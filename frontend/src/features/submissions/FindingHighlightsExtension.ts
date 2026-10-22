/**
 * ProseMirror 1-Indexed Token Position Translation & Inline DecorationSet Plugin.
 *
 * Coordinate translation invariant:
 * - Backend `Span(start, end)` is 0-indexed relative to a `TextNode.text` string.
 * - ProseMirror's flat document tree uses 1-indexed token positions where every
 *   block node (`<p>`, `<h1>`, `<li>`) adds `+1` opening token and `+1` closing token.
 * - Therefore, for a ProseMirror textblock starting at document offset `blockPos`
 *   with total `blockNodeSize` (where `blockNodeSize === textLength + 2`), a
 *   backend `Span(start, end)` maps to:
 *     `from = blockPos + 1 + span.start`
 *     `to   = Math.min(blockPos + 1 + span.end, blockPos + blockNodeSize - 1)`
 */

import type { FindingResponse } from "../../api/client";

export interface SpanLike {
  start: number;
  end: number;
}

export interface ProseMirrorRange {
  from: number;
  to: number;
}

/**
 * Pure coordinate translator from 0-indexed backend `Span(start, end)` to
 * 1-indexed ProseMirror textblock document coordinates.
 */
export function spanToProseMirrorRange(
  blockPos: number,
  blockNodeSize: number,
  span: SpanLike
): ProseMirrorRange | null {
  const maxContentPos = blockPos + Math.max(1, blockNodeSize - 1);
  const from = blockPos + 1 + Math.max(0, span.start);
  const to = Math.min(blockPos + 1 + Math.max(0, span.end), maxContentPos);
  if (from >= to) {
    return null;
  }
  return { from, to };
}

export interface ProseMirrorNodeLike {
  isBlock?: boolean;
  isTextblock?: boolean;
  nodeSize: number;
  descendants(
    callback: (node: ProseMirrorNodeLike, pos: number) => boolean | void
  ): void;
}

export interface DecorationSpec {
  from: number;
  to: number;
  attrs: Record<string, string>;
}

export interface FindingsPluginMeta {
  findings: FindingResponse[];
  paragraphNodeIds: string[];
  selectedRowId: number | null;
}

/**
 * Traverse a ProseMirror `doc` at the textblock level (`doc.descendants`)
 * and compute inline decoration specs for all open findings.
 */
export function computeFindingDecorationSpecs(
  doc: ProseMirrorNodeLike,
  meta: FindingsPluginMeta
): DecorationSpec[] {
  const specs: DecorationSpec[] = [];
  let blockIndex = 0;

  doc.descendants((node, pos) => {
    if (node.isBlock && node.isTextblock) {
      const nodeId = meta.paragraphNodeIds[blockIndex];
      blockIndex += 1;

      if (!nodeId) {
        return false;
      }

      for (const f of meta.findings) {
        if (f.node_id !== nodeId || f.resolution !== "open") {
          continue;
        }
        const loc = f.payload?.locator;
        if (
          loc &&
          typeof loc.start === "number" &&
          typeof loc.end === "number"
        ) {
          const range = spanToProseMirrorRange(pos, node.nodeSize, {
            start: loc.start,
            end: loc.end,
          });
          if (range) {
            const isBlocker = f.severity >= 50;
            const isSelected = f.row_id === meta.selectedRowId;
            specs.push({
              from: range.from,
              to: range.to,
              attrs: {
                class: [
                  "cg-finding-span",
                  isBlocker ? "cg-finding-blocker" : "cg-finding-warning",
                  isSelected ? "cg-finding-selected" : "",
                ]
                  .filter(Boolean)
                  .join(" "),
                "data-finding-row-id": String(f.row_id),
                title: `${f.check_id}: ${f.message}`,
              },
            });
          }
        }
      }
      // Stop recursion into child inline text nodes once handled at textblock level
      return false;
    }
    return true;
  });

  return specs;
}

/**
 * Factory that binds `computeFindingDecorationSpecs` into a live ProseMirror
 * `Plugin` + `DecorationSet` (compatible with `@tiptap/pm/state` and `@tiptap/pm/view`).
 */
export function createProseMirrorFindingsPlugin<
  TPluginKey,
  TDecoration,
  TDecorationSet extends {
    map(mapping: unknown, doc: unknown): TDecorationSet;
  },
>(pm: {
  pluginKey: TPluginKey;
  Decoration: {
    inline(
      from: number,
      to: number,
      attrs: Record<string, string>
    ): TDecoration;
  };
  DecorationSet: {
    empty: TDecorationSet;
    create(doc: unknown, decorations: TDecoration[]): TDecorationSet;
  };
  Plugin: new (spec: Record<string, unknown>) => unknown;
}) {
  return new pm.Plugin({
    key: pm.pluginKey,
    state: {
      init(): TDecorationSet {
        return pm.DecorationSet.empty;
      },
      apply(
        tr: {
          doc: ProseMirrorNodeLike;
          docChanged?: boolean;
          mapping?: unknown;
          getMeta(key: TPluginKey): FindingsPluginMeta | undefined;
        },
        oldSet: TDecorationSet
      ): TDecorationSet {
        const meta = tr.getMeta(pm.pluginKey);
        if (meta) {
          const specs = computeFindingDecorationSpecs(tr.doc, meta);
          const decorations = specs.map((s) =>
            pm.Decoration.inline(s.from, s.to, s.attrs)
          );
          return pm.DecorationSet.create(tr.doc, decorations);
        }
        if (tr.docChanged) {
          return oldSet.map(tr.mapping, tr.doc);
        }
        return oldSet;
      },
    },
    props: {
      decorations(state: unknown) {
        return (this as { getState(s: unknown): TDecorationSet }).getState(
          state
        );
      },
    },
  });
}
