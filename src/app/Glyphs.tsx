/**
 * The palette, spread across the page rather than dropped in a row.
 *
 * Six glyphs, given by hand, scattered as texture behind the reading. The
 * positions come from a fixed seed, so every visitor and every build gets the
 * same field and the page never jumps between renders. That is the difference
 * between a signature and confetti.
 *
 * Behind everything, unselectable, and hidden from a screen reader: it says
 * nothing, so it should not be read out. `fixed` rather than `absolute` so the
 * field stays still while the page scrolls over it, which keeps it reading as
 * paper rather than as objects in the layout.
 */

const PALETTE = ["💞", "🎀", "✨", "💘", "🍉", "💫"];

/** A small deterministic generator, so the field is the same one every time. */
function seeded(seed: number) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

const COUNT = 34;

const FIELD = (() => {
  const next = seeded(20260805);
  return Array.from({ length: COUNT }, (_, i) => ({
    glyph: PALETTE[i % PALETTE.length],
    left: next() * 100,
    top: next() * 100,
    size: 9 + next() * 9,
    // Kept low and varied. A glyph that competes with a sentence for attention
    // is not texture any more.
    opacity: 0.16 + next() * 0.2,
    tilt: (next() - 0.5) * 30,
  }));
})();

export function Glyphs() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 select-none overflow-hidden" aria-hidden>
      {FIELD.map((one, i) => (
        <span
          key={i}
          className="absolute"
          style={{
            left: `${one.left}%`,
            top: `${one.top}%`,
            fontSize: `${one.size}px`,
            opacity: one.opacity,
            transform: `rotate(${one.tilt}deg)`,
          }}
        >
          {one.glyph}
        </span>
      ))}
    </div>
  );
}
