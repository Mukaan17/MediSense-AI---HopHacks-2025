import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  User, 
  Weight, 
  Ruler, 
  Heart, 
  AlertTriangle,
  Plus,
  X,
  ChevronDown
} from 'lucide-react';
import { Patient } from '../types';

interface PatientFormProps {
  patient: Patient;
  onPatientChange: (patient: Patient) => void;
  className?: string;
}

const PatientForm: React.FC<PatientFormProps> = ({ patient, onPatientChange, className = '' }) => {
  const [expandedSections, setExpandedSections] = useState({
    demographics: true,
    vitals: false,
    history: false
  });

  const [newAllergy, setNewAllergy] = useState('');
  const [newMedication, setNewMedication] = useState('');
  const [newHistory, setNewHistory] = useState('');

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const updatePatient = (updates: Partial<Patient>) => {
    onPatientChange({ ...patient, ...updates });
  };

  const addAllergy = () => {
    if (newAllergy.trim()) {
      updatePatient({
        allergies: [...(patient.allergies || []), newAllergy.trim()]
      });
      setNewAllergy('');
    }
  };

  const removeAllergy = (index: number) => {
    const updated = [...(patient.allergies || [])];
    updated.splice(index, 1);
    updatePatient({ allergies: updated });
  };

  const addMedication = () => {
    if (newMedication.trim()) {
      updatePatient({
        medications: [...(patient.medications || []), newMedication.trim()]
      });
      setNewMedication('');
    }
  };

  const removeMedication = (index: number) => {
    const updated = [...(patient.medications || [])];
    updated.splice(index, 1);
    updatePatient({ medications: updated });
  };

  const addHistory = () => {
    if (newHistory.trim()) {
      updatePatient({
        pastMedicalHistory: [...(patient.pastMedicalHistory || []), newHistory.trim()]
      });
      setNewHistory('');
    }
  };

  const removeHistory = (index: number) => {
    const updated = [...(patient.pastMedicalHistory || [])];
    updated.splice(index, 1);
    updatePatient({ pastMedicalHistory: updated });
  };

  const getAgeCategory = (age?: number) => {
    if (!age) return null;
    if (age < 18) return { label: 'Pediatric', color: 'text-blue-600 bg-blue-50' };
    if (age >= 65) return { label: 'Geriatric', color: 'text-purple-600 bg-purple-50' };
    return { label: 'Adult', color: 'text-green-600 bg-green-50' };
  };

  const getBMICategory = (weight?: number, height?: number) => {
    if (!weight || !height) return null;
    const heightInMeters = height / 100;
    const bmi = weight / (heightInMeters * heightInMeters);
    
    if (bmi < 18.5) return { label: 'Underweight', color: 'text-blue-600 bg-blue-50' };
    if (bmi < 25) return { label: 'Normal', color: 'text-green-600 bg-green-50' };
    if (bmi < 30) return { label: 'Overweight', color: 'text-yellow-600 bg-yellow-50' };
    return { label: 'Obese', color: 'text-red-600 bg-red-50' };
  };

  const ageCategory = getAgeCategory(patient.age);
  const bmiCategory = getBMICategory(patient.weight, patient.height);

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Demographics Section */}
      <div className="border border-gray-200 rounded-lg">
        <button
          onClick={() => toggleSection('demographics')}
          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center space-x-2">
            <User className="h-4 w-4 text-medical-primary" />
            <span className="font-medium text-gray-900">Demographics</span>
            {ageCategory && (
              <span className={`text-xs px-2 py-1 rounded-full ${ageCategory.color}`}>
                {ageCategory.label}
              </span>
            )}
          </div>
          {expandedSections.demographics ? (
            <ChevronDown className="h-4 w-4 text-gray-500 rotate-180" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-500" />
          )}
        </button>
        
        <AnimatePresence>
          {expandedSections.demographics && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 border-t border-gray-100">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Age
                    </label>
                    <input
                      type="number"
                      value={patient.age || ''}
                      onChange={(e) => updatePatient({ age: parseInt(e.target.value) || undefined })}
                      className="input-field"
                      placeholder="Enter age"
                      min="0"
                      max="120"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Gender
                    </label>
                    <select
                      value={patient.gender || ''}
                      onChange={(e) => updatePatient({ gender: e.target.value as any })}
                      className="input-field"
                    >
                      <option value="">Select gender</option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Pregnancy Status
                    </label>
                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={patient.pregnant || false}
                        onChange={(e) => updatePatient({ pregnant: e.target.checked })}
                        className="rounded border-gray-300 text-medical-primary focus:ring-medical-primary"
                      />
                      <span className="text-sm text-gray-700">Pregnant</span>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Vitals Section */}
      <div className="border border-gray-200 rounded-lg">
        <button
          onClick={() => toggleSection('vitals')}
          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center space-x-2">
            <Heart className="h-4 w-4 text-medical-primary" />
            <span className="font-medium text-gray-900">Vital Signs</span>
            {bmiCategory && (
              <span className={`text-xs px-2 py-1 rounded-full ${bmiCategory.color}`}>
                BMI: {bmiCategory.label}
              </span>
            )}
          </div>
          {expandedSections.vitals ? (
            <ChevronDown className="h-4 w-4 text-gray-500 rotate-180" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-500" />
          )}
        </button>
        
        <AnimatePresence>
          {expandedSections.vitals && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 border-t border-gray-100">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      <Weight className="h-4 w-4 inline mr-1" />
                      Weight (kg)
                    </label>
                    <input
                      type="number"
                      value={patient.weight || ''}
                      onChange={(e) => updatePatient({ weight: parseFloat(e.target.value) || undefined })}
                      className="input-field"
                      placeholder="Enter weight"
                      min="0"
                      step="0.1"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      <Ruler className="h-4 w-4 inline mr-1" />
                      Height (cm)
                    </label>
                    <input
                      type="number"
                      value={patient.height || ''}
                      onChange={(e) => updatePatient({ height: parseFloat(e.target.value) || undefined })}
                      className="input-field"
                      placeholder="Enter height"
                      min="0"
                      step="0.1"
                    />
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Medical History Section */}
      <div className="border border-gray-200 rounded-lg">
        <button
          onClick={() => toggleSection('history')}
          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-medical-primary" />
            <span className="font-medium text-gray-900">Medical History</span>
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
              {((patient.allergies?.length || 0) + (patient.medications?.length || 0) + (patient.pastMedicalHistory?.length || 0))} items
            </span>
          </div>
          {expandedSections.history ? (
            <ChevronDown className="h-4 w-4 text-gray-500 rotate-180" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-500" />
          )}
        </button>
        
        <AnimatePresence>
          {expandedSections.history && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 border-t border-gray-100">
                <div className="space-y-4 pt-4">
                  {/* Allergies */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Allergies
                    </label>
                    <div className="space-y-2">
                      {patient.allergies?.map((allergy, index) => (
                        <div key={index} className="flex items-center space-x-2">
                          <span className="flex-1 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                            {allergy}
                          </span>
                          <button
                            onClick={() => removeAllergy(index)}
                            className="p-1 text-red-600 hover:text-red-800"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                      <div className="flex space-x-2">
                        <input
                          type="text"
                          value={newAllergy}
                          onChange={(e) => setNewAllergy(e.target.value)}
                          className="input-field flex-1"
                          placeholder="Add allergy"
                          onKeyPress={(e) => e.key === 'Enter' && addAllergy()}
                        />
                        <button
                          onClick={addAllergy}
                          className="btn-primary px-3 py-2"
                        >
                          <Plus className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Medications */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Current Medications
                    </label>
                    <div className="space-y-2">
                      {patient.medications?.map((medication, index) => (
                        <div key={index} className="flex items-center space-x-2">
                          <span className="flex-1 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
                            {medication}
                          </span>
                          <button
                            onClick={() => removeMedication(index)}
                            className="p-1 text-blue-600 hover:text-blue-800"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                      <div className="flex space-x-2">
                        <input
                          type="text"
                          value={newMedication}
                          onChange={(e) => setNewMedication(e.target.value)}
                          className="input-field flex-1"
                          placeholder="Add medication"
                          onKeyPress={(e) => e.key === 'Enter' && addMedication()}
                        />
                        <button
                          onClick={addMedication}
                          className="btn-primary px-3 py-2"
                        >
                          <Plus className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Past Medical History */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Past Medical History
                    </label>
                    <div className="space-y-2">
                      {patient.pastMedicalHistory?.map((history, index) => (
                        <div key={index} className="flex items-center space-x-2">
                          <span className="flex-1 px-3 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
                            {history}
                          </span>
                          <button
                            onClick={() => removeHistory(index)}
                            className="p-1 text-green-600 hover:text-green-800"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                      <div className="flex space-x-2">
                        <input
                          type="text"
                          value={newHistory}
                          onChange={(e) => setNewHistory(e.target.value)}
                          className="input-field flex-1"
                          placeholder="Add medical history"
                          onKeyPress={(e) => e.key === 'Enter' && addHistory()}
                        />
                        <button
                          onClick={addHistory}
                          className="btn-primary px-3 py-2"
                        >
                          <Plus className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default PatientForm;
