import { normalizeHUD } from './wsClient';

describe('normalizeHUD', () => {
  it('derives ranked from fusion.top10 when absent', () => {
    const hud = normalizeHUD({
      dx: 'pneumonia_unspecified',
      fusion: {
        top10: [
          { condition: 'pneumonia_unspecified', score: 0.79, why: 'combined evidence' },
          { condition: 'acute_bronchitis', score: 0.55, why: 'combined evidence' },
        ],
      },
    });
    expect(hud.ranked).toHaveLength(2);
    expect(hud.ranked![0]).toEqual({
      condition: 'pneumonia_unspecified',
      confidence: 0.79,
      reason: 'combined evidence',
    });
  });

  it('keeps an existing ranked list untouched', () => {
    const ranked = [{ condition: 'x', confidence: 0.5 }];
    const hud = normalizeHUD({ ranked, fusion: { top10: [{ condition: 'y', score: 0.9 }] } });
    expect(hud.ranked).toBe(ranked);
  });

  it('caps derived ranked at five entries', () => {
    const top10 = Array.from({ length: 10 }, (_, i) => ({ condition: `c${i}`, score: 0.9 - i * 0.05 }));
    expect(normalizeHUD({ fusion: { top10 } }).ranked).toHaveLength(5);
  });

  it('tolerates empty payloads', () => {
    expect(normalizeHUD(null)).toEqual({});
  });
});
