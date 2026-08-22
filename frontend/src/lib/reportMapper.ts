// Maps raw backend inference responses (fusion + structured diagnosis +
// advisory + evidence payloads) into the UI's ClinicalReport shape.
// Pure function: kept out of the component tree so it is unit-testable.
import { ClinicalReport } from '../types';

export const processAPIResponse = (data: any): ClinicalReport => {
  const advisory = data?.rag_advisory;
  const advisorySummary =
    typeof advisory === 'string'
      ? advisory
      : (advisory?.follow_up || '');

  // Process the actual backend response
  const report: ClinicalReport = {
    patientSummary: data.summary || advisorySummary || "Clinical analysis completed",
    differentialDiagnosis: [],
    redFlagAlerts: [],
    recommendations: [],
    followUp: "",
    patientEducation: [],
    citations: [],
    generatedAt: new Date().toISOString(),
    confidence: 0.0
  };

  // Process differential diagnosis from backend
  if (data.fusion?.top10) {
    report.differentialDiagnosis = data.fusion.top10.slice(0, 5).map((item: any) => ({
      condition: item.condition,
      probability: item.score || 0.0,
      confidence: item.score || 0.0,
      riskFactors: item.risk_factors || [],
      redFlags: item.red_flags || [],
      supportingEvidence: [item.why || 'Combined evidence'],
      reasoning: item.why || 'Based on multimodal analysis'
    }));
  }

  // Process structured diagnosis if available
  if (data.structured_diagnosis) {
    const structured = data.structured_diagnosis;
    
    // Update patient summary
    if (data.summary) {
      report.patientSummary = data.summary;
    } else if (structured.summary) {
      report.patientSummary = structured.summary;
    }
    
    // Process differential diagnosis from structured response
    if (structured.differential_diagnosis && structured.differential_diagnosis.top_3_diagnoses) {
      report.differentialDiagnosis = structured.differential_diagnosis.top_3_diagnoses.map((diag: any) => ({
        condition: diag.condition || diag.diagnosis,
        probability: diag.probability || diag.confidence || 0.0,
        confidence: diag.confidence || diag.probability || 0.0,
        riskFactors: diag.risk_factors || [],
        redFlags: diag.red_flags || [],
        supportingEvidence: diag.supporting_evidence || [diag.reasoning || 'Clinical evidence'],
        reasoning: diag.reasoning || diag.explanation || 'Based on clinical analysis'
      }));
    }
    
    // Process recommendations
    if (structured.recommendations) {
      report.recommendations = structured.recommendations;
    } else {
      // Fallback: extract recommendations from next_steps in diagnoses
      const nextStepsRecommendations: string[] = [];
      if (structured.differential_diagnosis && structured.differential_diagnosis.top_3_diagnoses) {
        structured.differential_diagnosis.top_3_diagnoses.forEach((diag: any) => {
          if (diag.next_steps && Array.isArray(diag.next_steps)) {
            nextStepsRecommendations.push(...diag.next_steps);
          }
        });
      }
      
      // Also extract from follow_up_plan if available
      if (structured.clinical_workflow?.follow_up_plan) {
        structured.clinical_workflow.follow_up_plan.forEach((plan: any) => {
          if (plan.actions && Array.isArray(plan.actions)) {
            nextStepsRecommendations.push(...plan.actions);
          }
        });
      }
      
      if (nextStepsRecommendations.length > 0) {
        report.recommendations = nextStepsRecommendations;
      }
    }
    
    // Process follow-up
    if (structured.follow_up) {
      report.followUp = structured.follow_up;
    } else if (structured.clinical_workflow?.follow_up_plan) {
      // Fallback: format follow_up_plan as text
      const followUpText = structured.clinical_workflow.follow_up_plan
        .map((plan: any) => `${plan.timeline}: ${plan.reason}`)
        .join('; ');
      if (followUpText) {
        report.followUp = followUpText;
      }
    }
  }

  // Process recommendations from backend (note: first_steps_non_prescriptive is stripped from answer endpoint)
  if (data.answer?.first_steps_non_prescriptive) {
    report.recommendations = data.answer.first_steps_non_prescriptive;
  }
  
  // Fallback: if no recommendations found, generate basic ones from differential diagnosis
  if (report.recommendations.length === 0 && report.differentialDiagnosis.length > 0) {
    const fallbackRecommendations: string[] = [];
    
    // Add basic recommendations based on top diagnoses
    report.differentialDiagnosis.slice(0, 3).forEach((diag, index) => {
      if (diag.confidence > 0.5) {
        fallbackRecommendations.push(`Consider evaluation for ${diag.condition.replace(/_/g, ' ')}`);
      }
    });
    
    // Add general recommendations
    if (fallbackRecommendations.length === 0) {
      fallbackRecommendations.push("Obtain detailed history and physical examination");
      fallbackRecommendations.push("Consider appropriate diagnostic workup based on clinical presentation");
      fallbackRecommendations.push("Monitor patient response to initial interventions");
    }
    
    report.recommendations = fallbackRecommendations;
  }

  // Process follow-up from backend
  if (data.answer?.follow_up) {
    report.followUp = data.answer.follow_up;
  }

  // Process citations from backend
  if (data.answer?.citations) {
    report.citations = data.answer.citations;
  }

  // Process red flags from backend
  if (data.answer?.red_flags_to_screen) {
    report.redFlagAlerts = data.answer.red_flags_to_screen.map((flag: string) => ({
      alert: flag,
      severity: 'medium' as const,
      trigger: flag,
      action: 'Clinical assessment recommended'
    }));
  }

  // Process risk analysis red flags
  if (data.risk_analysis?.red_flag_alerts) {
    report.redFlagAlerts = data.risk_analysis.red_flag_alerts.map((alert: any) => ({
      alert: alert.alert || alert.message,
      severity: alert.severity || 'medium',
      trigger: alert.trigger || alert.condition,
      action: alert.action || 'Clinical assessment recommended',
      condition: alert.condition
    }));
  }

  // Calculate overall confidence
  if (report.differentialDiagnosis.length > 0) {
    report.confidence = report.differentialDiagnosis.reduce((sum, d) => sum + d.confidence, 0) / report.differentialDiagnosis.length;
  } else if (data.fusion?.top_confidence) {
    report.confidence = data.fusion.top_confidence;
  }

  // Explainability from the backend's real evidence payload (posterior
  // shifts + fused scores + citations). The breakdown values are grounded
  // signals: top imaging score, fused text confidence, and coverage-scaled
  // indicators for retrieved citations and attached EHR context.
  const shift = data.evidence?.posterior_shift;
  const reasoningChain: string[] = [];
  if (data.fusion?.top10?.length) {
    const top = data.fusion.top10[0];
    reasoningChain.push(`Fused image + text evidence ranks ${String(top.condition).replace(/_/g, ' ')} first (score ${(top.score ?? 0).toFixed(2)})`);
  }
  if (shift?.shift_reasons?.length) {
    reasoningChain.push(...shift.shift_reasons);
  }
  if (shift?.base_top && shift?.adjusted_top && shift.base_top.condition !== shift.adjusted_top.condition) {
    reasoningChain.push(`Evidence shifted the leading consideration from ${shift.base_top.condition} to ${shift.adjusted_top.condition}`);
  }
  if (reasoningChain.length > 0) {
    const imageScores = (data.image_findings || []).map((f: any) => f.score || 0);
    report.xai = {
      reasoningChain,
      confidenceBreakdown: {
        clinicalGuidelines: Math.min(1, (report.citations?.length || 0) * 0.2),
        imagingEvidence: imageScores.length ? Math.max(...imageScores) : 0,
        symptomMatch: data.fusion?.top_confidence ?? 0,
        patientHistory: data.ehr ? Math.min(1, 0.3 + (shift?.shift_reasons?.length || 0) * 0.1) : 0,
      },
      sourceAttribution: (report.citations || []).slice(0, 5).map((c: string) => {
        const [source, section] = String(c).split('§').map((s) => s.trim());
        return { source: source || String(c), section: section || '', relevance: 0.5, type: 'study' as const };
      }),
    };
  }

  return report;
};
