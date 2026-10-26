/**
 * ProseMirror & React UTF-16 Span Coordinate Translation Utilities + Tiptap Extension.
 *
 * Converts 0-indexed Python Unicode codepoint offsets (`Span(start, end)`)
 * into exact JavaScript UTF-16 string slices and ProseMirror positions so
 * astral-plane characters (emojis, symbols) never drift, and wires a live
 * ProseMirror `DecorationSet` plugin into Tiptap (`@tiptap/react`).
 */

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { FindingItem } from "../../api/client";

export type FindingResponse = FindingItem;

export interface SpanLike {
  start: number;
  end: number;
}

export interface ProseMirrorRange {
  from: number;
  to: number;
}

/**
 * Convert a 0-indexed Unicode codepoint offset (from Python) into a 0-indexed
 * UTF-16 code-unit offset (for JavaScript / ProseMirror) within `text`.
 */
export function codepointIndexToUtf16Offset(
  text: string,
  codepointIndex: number,
): number {
  if (codepointIndex <= 0) {
    return 0;
  }
  let cpCount = 0;
  let utf16Offset = 0;
  for (const ch of text) {
    if (cpCount >= codepointIndex) {
      break;
    }
    utf16Offset += ch.length; // 2 for astral-plane surrogate pairs, 1 for BMP
    cpCount += 1;
  }
  return utf16Offset;
}

/**
 * Pure coordinate translator from 0-indexed backend `Span(start, end)` (in
 * Python Unicode codepoints) to 1-indexed ProseMirror textblock document coordinates.
 */
export function spanToProseMirrorRange(
  blockPos: number,
  blockNodeSize: number,
  span: SpanLike,
  blockText?: string,
): ProseMirrorRange | null {
  const maxContentPos = blockPos + Math.max(1, blockNodeSize - 1);
  const startOffset =
    blockText !== undefined
      ? codepointIndexToUtf16Offset(blockText, Math.max(0, span.start))
      : Math.max(0, span.start);
  const endOffset =
    blockText !== undefined
      ? codepointIndexToUtf16Offset(blockText, Math.max(0, span.end))
      : Math.max(0, span.end);

  const from = blockPos + 1 + startOffset;
  const to = Math.min(blockPos + 1 + endOffset, maxContentPos);
  if (from >= to) {
    return null;
  }
  return { from, to };
}

export interface ProseMirrorNodeLike {
  isBlock?: boolean;
  isTextblock?: boolean;
  textContent?: string;
  nodeSize: number;
  descendants(
    callback: (node: ProseMirrorNodeLike, pos: number) => boolean | void,
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
 * and compute inline decoration specs for all findings.
 */
export function computeFindingDecorationSpecs(
  doc: ProseMirrorNodeLike,
  meta: FindingsPluginMeta,
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
        if (f.node_id !== nodeId) {
          continue;
        }
        const loc = f.payload?.locator;
        if (
          loc &&
          typeof loc.start === "number" &&
          typeof loc.end === "number"
        ) {
          const range = spanToProseMirrorRange(
            pos,
            node.nodeSize,
            { start: loc.start, end: loc.end },
            node.textContent,
          );
          if (range) {
            const isBlocker = f.severity >= 50;
            const isSelected = f.row_id === meta.selectedRowId;
            const isResolved = f.resolution !== "open";
            specs.push({
              from: range.from,
              to: range.to,
              attrs: {
                class: [
                  "cg-finding-span",
                  "finding-inline-mark",
                  isResolved
                    ? "finding-mark-resolved"
                    : isBlocker
                      ? "cg-finding-blocker finding-mark-blocker"
                      : "cg-finding-warning finding-mark-warning",
                  isSelected ? "cg-finding-selected finding-mark-selected" : "",
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
      return false;
    }
    return true;
  });

  return specs;
}

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
      attrs: Record<string, string>,
    ): TDecoration;
  };
  DecorationSet: {
    empty: TDecorationSet;
    create(doc: unknown, decorations: TDecoration[]): TDecorationSet;
  };
  Plugin: new (spec: Record<string, unknown>) => unknown;
  onSelectFinding?: (rowId: number) => void;
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
        oldSet: TDecorationSet,
      ): TDecorationSet {
        const meta = tr.getMeta(pm.pluginKey);
        if (meta) {
          const specs = computeFindingDecorationSpecs(tr.doc, meta);
          const decorations = specs.map((s) =>
            pm.Decoration.inline(s.from, s.to, s.attrs),
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
          state,
        );
      },
      handleClick(_view: unknown, _pos: number, event: MouseEvent) {
        if (!pm.onSelectFinding) return false;
        const target = event.target as HTMLElement | null;
        const spanEl = target?.closest?.("[data-finding-row-id]");
        const rawRowId = spanEl?.getAttribute("data-finding-row-id");
        if (rawRowId) {
          const parsed = Number(rawRowId);
          if (!Number.isNaN(parsed)) {
            pm.onSelectFinding(parsed);
            return true;
          }
        }
        return false;
      },
    },
  });
}

export interface FindingDecorationRange {
  rowId: number;
  findingId: string;
  from: number;
  to: number;
  severity: number;
  resolution: string;
}

export const findingHighlightsKey = "canongateFindingHighlights";
export const findingHighlightsPluginKey = new PluginKey(findingHighlightsKey);

export interface FindingHighlightsOptions {
  onSelectFinding?: (rowId: number) => void;
}

export const FindingHighlightsExtension =
  Extension.create<FindingHighlightsOptions>({
    name: "findingHighlights",
    addOptions() {
      return {
        onSelectFinding: undefined,
      };
    },
    addProseMirrorPlugins() {
      const onSelect = this.options.onSelectFinding;
      const plugin = createProseMirrorFindingsPlugin({
        pluginKey: findingHighlightsPluginKey,
        Decoration: Decoration as unknown as {
          inline(
            from: number,
            to: number,
            attrs: Record<string, string>,
          ): Decoration;
        },
        DecorationSet: DecorationSet as unknown as {
          empty: DecorationSet;
          create(doc: unknown, decorations: Decoration[]): DecorationSet;
        },
        Plugin: Plugin as unknown as new (
          spec: Record<string, unknown>,
        ) => Plugin,
        onSelectFinding: onSelect,
      });
      return [plugin as Plugin];
    },
  });
