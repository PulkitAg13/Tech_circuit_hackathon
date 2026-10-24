import { useState, useEffect, useRef, useCallback } from "react";

export interface SlideItem {
  id: number;
  title: string;
  tag: string;
  src: string;
  alt: string;
}

const SLIDES: SlideItem[] = [
  {
    id: 1,
    title: "Detect Issues Early, Protect Your Brand",
    tag: "Zero-AI Optical & Math Linting",
    src: "/slides/slide-1.png",
    alt: "Detect Issues Early, Protect Your Brand — CanonGate Automated Pre-Publication Governance",
  },
  {
    id: 2,
    title: "Every Campaign, Every Claim Checked",
    tag: "Pre-Publication Multi-Modal Auditing",
    src: "/slides/slide-2.png",
    alt: "Every Campaign, Every Claim Checked — Full Text & Fine-Print Verification",
  },
  {
    id: 3,
    title: "From Creative Ideas to Compliant Campaigns",
    tag: "Slot-Level Entailment & Condition Caps",
    src: "/slides/slide-3.png",
    alt: "From Creative Ideas to Compliant Campaigns — Drop Cap & Misleading Omission Auditing",
  },
  {
    id: 4,
    title: "Safe Campaigns, Stronger Brands",
    tag: "ASCI, CCPA & RBI Rulebook Alignment",
    src: "/slides/slide-4.png",
    alt: "Safe Campaigns, Stronger Brands — Statutory Legal Alignment Before Spend",
  },
  {
    id: 5,
    title: "Smarter Suggestions, Human Approval",
    tag: "Constrained Surgical Rewriter with PII Masking",
    src: "/slides/slide-5.png",
    alt: "Smarter Suggestions, Human Approval — Human-in-the-Loop Safe Governance",
  },
];

const SLIDE_DURATION_MS = 5000; // Exactly 5 seconds duration per slide

export function ImageSlideshow() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<number | null>(null);

  const nextSlide = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % SLIDES.length);
    setProgress(0);
    startTimeRef.current = Date.now();
  }, []);

  const prevSlide = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + SLIDES.length) % SLIDES.length);
    setProgress(0);
    startTimeRef.current = Date.now();
  }, []);

  const goToSlide = useCallback((index: number) => {
    setCurrentIndex(index);
    setProgress(0);
    startTimeRef.current = Date.now();
  }, []);

  // 5-second automatic sliding loop with progress bar animation
  useEffect(() => {
    if (startTimeRef.current === 0) {
      startTimeRef.current = Date.now();
    }
    if (isPaused) return;

    startTimeRef.current = Date.now() - (progress / 100) * SLIDE_DURATION_MS;

    const interval = window.setInterval(() => {
      const elapsed = Date.now() - startTimeRef.current;
      const currentProgress = Math.min((elapsed / SLIDE_DURATION_MS) * 100, 100);
      setProgress(currentProgress);

      if (elapsed >= SLIDE_DURATION_MS) {
        nextSlide();
      }
    }, 50);

    timerRef.current = interval;

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isPaused, nextSlide, progress]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") {
      prevSlide();
    } else if (e.key === "ArrowRight") {
      nextSlide();
    }
  };

  return (
    <section 
      className="slideshow-wrapper" 
      aria-label="Platform Highlights Slideshow"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <div className="slideshow-container">
        {/* Main Stage with 2.5:1 Widescreen Aspect Ratio */}
        <div className="slideshow-stage">
          {SLIDES.map((slide, index) => {
            const isActive = index === currentIndex;
            return (
              <div
                key={slide.id}
                className={`slideshow-slide ${isActive ? "active" : ""}`}
                aria-hidden={!isActive}
              >
                <img
                  src={slide.src}
                  alt={slide.alt}
                  className="slideshow-image"
                  loading={index === 0 ? "eager" : "lazy"}
                />
              </div>
            );
          })}

          {/* Previous Arrow Button */}
          <button
            type="button"
            className="slideshow-nav-btn btn-prev"
            onClick={prevSlide}
            aria-label="Previous Slide"
            title="Previous Slide"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>

          {/* Next Arrow Button */}
          <button
            type="button"
            className="slideshow-nav-btn btn-next"
            onClick={nextSlide}
            aria-label="Next Slide"
            title="Next Slide"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </button>
        </div>

        {/* 5-Second Timer Progress Bar & Interactive Slide Indicators */}
        <div className="slideshow-footer-controls">
          <div className="slideshow-indicators" role="tablist">
            {SLIDES.map((slide, index) => {
              const isActive = index === currentIndex;
              return (
                <button
                  key={slide.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={`slideshow-dot-btn ${isActive ? "active" : ""}`}
                  onClick={() => goToSlide(index)}
                  title={`Jump to slide ${index + 1}: ${slide.title}`}
                >
                  <div className="dot-track">
                    {isActive && (
                      <div
                        className="dot-progress-fill"
                        style={{ width: `${progress}%` }}
                      />
                    )}
                  </div>
                  <span className="dot-label">{slide.id}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
