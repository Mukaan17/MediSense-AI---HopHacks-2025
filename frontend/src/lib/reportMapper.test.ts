import { processAPIResponse } from './reportMapper';

describe('processAPIResponse', () => {
  it('maps fusion.top10 into the differential', () => {
    const report = processAPIResponse({
      summary: 'Analysis done',
      fusion: {
        top10: [
          { condition: 'pneumonia_unspecified', score: 0.79, why: 'combined evidence' },
          { condition: 'acute_bronchitis', score: 0.55, why: 'combined evidence' },
        ],
        top_confidence: 0.79,
      },
    });
    expect(report.patientSummary).toBe('Analysis done');
    expect(report.differentialDiagnosis).toHaveLength(2);
    expect(report.differentialDiagnosis[0].condition).toBe('pneumonia_unspecified');
    expect(report.confidence).toBeCloseTo(0.67, 2);
  });

  it('prefers the structured differential when present', () => {
    const report = processAPIResponse({
      fusion: { top10: [{ condition: 'x', score: 0.4 }] },
      structured_diagnosis: {
        differential_diagnosis: {
          top_3_diagnoses: [
            { condition: 'heart_failure_exacerbation', confidence: 0.8, supporting_evidence: ['edema'] },
          ],
        },
        recommendations: ['Obtain BNP'],
        follow_up: '48 hours',
      },
    });
    expect(report.differentialDiagnosis[0].condition).toBe('heart_failure_exacerbation');
    expect(report.recommendations).toEqual(['Obtain BNP']);
    expect(report.followUp).toBe('48 hours');
  });

  it('builds XAI from the real evidence payload', () => {
    const report = processAPIResponse({
      ehr: { patient_id: 'MIMIC_1' },
      fusion: { top10: [{ condition: 'pneumonia_unspecified', score: 0.65 }], top_confidence: 0.65 },
      image_findings: [{ label: 'Pneumonia', score: 0.7 }],
      answer: { citations: ['English Train.json §item_5.c1'] },
      evidence: {
        posterior_shift: {
          base_top: { condition: 'uri', score: 0.5 },
          adjusted_top: { condition: 'pneumonia_unspecified', score: 0.65 },
          shift_reasons: ['EHR fever 101.5F -> pneumonia_unspecified (+0.22)'],
        },
      },
    });
    expect(report.xai).toBeDefined();
    expect(report.xai!.reasoningChain.join(' ')).toContain('fever 101.5F');
    expect(report.xai!.confidenceBreakdown.imagingEvidence).toBeCloseTo(0.7);
    expect(report.xai!.sourceAttribution[0].source).toBe('English Train.json');
    expect(report.xai!.sourceAttribution[0].section).toBe('item_5.c1');
  });

  it('produces fallback recommendations when the backend sends none', () => {
    const report = processAPIResponse({
      fusion: { top10: [{ condition: 'asthma_exacerbation', score: 0.72 }] },
    });
    expect(report.recommendations.length).toBeGreaterThan(0);
  });

  it('omits XAI when no evidence exists', () => {
    expect(processAPIResponse({}).xai).toBeUndefined();
  });
});
