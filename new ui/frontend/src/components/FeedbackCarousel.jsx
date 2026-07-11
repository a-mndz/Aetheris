import { useState } from "react";
import { ChevronLeft, ChevronRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { HOME_TESTIMONIALS } from "../constants/homeContent.js";
import { picsum } from "../utils/id.js";

function FeedbackCarousel({ onOpenSettings, onOpenTelemetry, onFocusInput }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const active = HOME_TESTIMONIALS[activeIndex];

  function shift(step) {
    setActiveIndex((current) => (current + step + HOME_TESTIMONIALS.length) % HOME_TESTIMONIALS.length);
  }

  return (
    <section className="chapter section-carousel">
      <div className="carousel-shell">
        <div className="carousel-copy">
          <p className="section-kicker">Teams use it when the room is moving too fast for memory to stay honest.</p>
          <h2>What changes once the reasoning is visible.</h2>
          <p className="section-body">The interface stays quiet. The conversation stops collapsing into the loudest summary.</p>
          <div className="carousel-actions">
            <button className="icon-rail-btn" onClick={() => shift(-1)} aria-label="Previous testimonial"><ChevronLeft size={16} /></button>
            <button className="icon-rail-btn" onClick={() => shift(1)} aria-label="Next testimonial"><ChevronRight size={16} /></button>
          </div>
        </div>

        <div className="carousel-panel">
          <div className="portrait-stack" aria-hidden="true">
            {HOME_TESTIMONIALS.map((item, index) => (
              <button
                key={item.author}
                type="button"
                className={`portrait-chip${index === activeIndex ? " active" : ""}`}
                onClick={() => setActiveIndex(index)}
                aria-label={`Show testimonial from ${item.author}`}
              >
                <img src={picsum(item.image, 320, 320)} alt="" />
              </button>
            ))}
          </div>

          <div className="quote-card hover-card">
            <div className="quote-card-media overflow-clip">
              <img src={picsum(active.image, 900, 1200)} alt="" className="hover-media" />
            </div>
            <div className="quote-card-body">
              <p className="quote-mark">Testimonial</p>
              <blockquote>{active.quote}</blockquote>
              <div className="quote-meta">
                <div>
                  <div className="quote-author">{active.author}</div>
                  <div className="quote-role">{active.role}</div>
                </div>
                <button className="footer-link" onClick={onOpenTelemetry}>Open telemetry <ArrowUpRight size={14} /></button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="footer-cta">
        <div>
          <p className="section-kicker">Ready when the argument gets expensive.</p>
          <h2>Start a live thread before the meeting turns into a recap.</h2>
        </div>
        <div className="footer-cta-actions">
          <button className="btn-primary footer-main-btn" onClick={onFocusInput}>Open a blank thread <ArrowRight size={15} /></button>
          <button className="footer-link" onClick={onOpenSettings}>Settings</button>
          <button className="footer-link" onClick={onOpenTelemetry}>Telemetry</button>
        </div>
      </div>
    </section>
  );
}

export default FeedbackCarousel;
