import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  AlertTriangle, 
  X, 
  Clock, 
  Shield, 
  Activity,
  Heart,
  Brain,
  Zap
} from 'lucide-react';
import { RedFlagAlert as RedFlagAlertType } from '../types';

interface RedFlagAlertsProps {
  alerts: RedFlagAlertType[];
  className?: string;
}

const RedFlagAlerts: React.FC<RedFlagAlertsProps> = ({ alerts, className = '' }) => {
  const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(new Set());

  const dismissAlert = (alert: string) => {
    setDismissedAlerts(prev => {
      const newSet = new Set(prev);
      newSet.add(alert);
      return newSet;
    });
  };

  const getSeverityConfig = (severity: string) => {
    switch (severity) {
      case 'critical':
        return {
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200',
          textColor: 'text-red-800',
          iconColor: 'text-red-600',
          icon: Heart,
          pulse: true
        };
      case 'high':
        return {
          bgColor: 'bg-orange-50',
          borderColor: 'border-orange-200',
          textColor: 'text-orange-800',
          iconColor: 'text-orange-600',
          icon: AlertTriangle,
          pulse: true
        };
      case 'medium':
        return {
          bgColor: 'bg-yellow-50',
          borderColor: 'border-yellow-200',
          textColor: 'text-yellow-800',
          iconColor: 'text-yellow-600',
          icon: Shield,
          pulse: false
        };
      case 'low':
        return {
          bgColor: 'bg-blue-50',
          borderColor: 'border-blue-200',
          textColor: 'text-blue-800',
          iconColor: 'text-blue-600',
          icon: Activity,
          pulse: false
        };
      default:
        return {
          bgColor: 'bg-gray-50',
          borderColor: 'border-gray-200',
          textColor: 'text-gray-800',
          iconColor: 'text-gray-600',
          icon: AlertTriangle,
          pulse: false
        };
    }
  };

  const getSeverityLabel = (severity: string) => {
    switch (severity) {
      case 'critical': return 'CRITICAL';
      case 'high': return 'HIGH PRIORITY';
      case 'medium': return 'MEDIUM PRIORITY';
      case 'low': return 'LOW PRIORITY';
      default: return 'ALERT';
    }
  };

  const getConditionIcon = (condition?: string) => {
    if (!condition) return null;
    
    const conditionLower = condition.toLowerCase();
    if (conditionLower.includes('cardiac') || conditionLower.includes('heart')) {
      return <Heart className="h-4 w-4" />;
    }
    if (conditionLower.includes('stroke') || conditionLower.includes('neuro')) {
      return <Brain className="h-4 w-4" />;
    }
    if (conditionLower.includes('emergency') || conditionLower.includes('urgent')) {
      return <Zap className="h-4 w-4" />;
    }
    return <Activity className="h-4 w-4" />;
  };

  const visibleAlerts = alerts.filter(alert => !dismissedAlerts.has(alert.alert));

  if (visibleAlerts.length === 0) {
    return null;
  }

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-center space-x-2">
        <AlertTriangle className="h-6 w-6 text-red-600" />
        <h3 className="text-lg font-semibold text-gray-900">
          Clinical Alerts
        </h3>
        <span className="text-sm text-red-600 bg-red-100 px-2 py-1 rounded-full font-medium">
          {visibleAlerts.length} Active
        </span>
      </div>

      <div className="space-y-3">
        {visibleAlerts.map((alert, index) => {
          const config = getSeverityConfig(alert.severity);
          const IconComponent = config.icon;
          const ConditionIcon = getConditionIcon(alert.condition);

          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              className={`${config.bgColor} ${config.borderColor} border-2 rounded-lg p-4 relative ${
                config.pulse ? 'animate-pulse' : ''
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3 flex-1">
                  <div className={`${config.iconColor} flex-shrink-0`}>
                    <IconComponent className="h-6 w-6" />
                  </div>
                  
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-2">
                      <h4 className={`font-bold text-lg ${config.textColor}`}>
                        {alert.alert}
                      </h4>
                      <span className={`text-xs font-semibold px-2 py-1 rounded-full ${config.bgColor} ${config.textColor} border ${config.borderColor}`}>
                        {getSeverityLabel(alert.severity)}
                      </span>
                      {ConditionIcon && (
                        <div className={config.iconColor}>
                          {ConditionIcon}
                        </div>
                      )}
                    </div>
                    
                    <div className="space-y-2">
                      <div>
                        <span className={`text-sm font-medium ${config.textColor}`}>
                          Trigger: 
                        </span>
                        <span className={`text-sm ${config.textColor} ml-1`}>
                          {alert.trigger}
                        </span>
                      </div>
                      
                      <div>
                        <span className={`text-sm font-medium ${config.textColor}`}>
                          Recommended Action: 
                        </span>
                        <span className={`text-sm ${config.textColor} ml-1`}>
                          {alert.action}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <button
                  onClick={() => dismissAlert(alert.alert)}
                  className={`${config.textColor} hover:opacity-70 transition-opacity flex-shrink-0 ml-2`}
                  title="Dismiss alert"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Critical alerts get special treatment */}
              {alert.severity === 'critical' && (
                <div className="mt-3 pt-3 border-t border-red-200">
                  <div className="flex items-center space-x-2">
                    <Clock className="h-4 w-4 text-red-600" />
                    <span className="text-sm font-medium text-red-800">
                      Immediate attention required - Consider emergency protocols
                    </span>
                  </div>
                </div>
              )}

              {/* High priority alerts get action emphasis */}
              {alert.severity === 'high' && (
                <div className="mt-3 pt-3 border-t border-orange-200">
                  <div className="flex items-center space-x-2">
                    <Activity className="h-4 w-4 text-orange-600" />
                    <span className="text-sm font-medium text-orange-800">
                      Urgent assessment recommended within 24 hours
                    </span>
                  </div>
                </div>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Summary for multiple alerts */}
      {visibleAlerts.length > 1 && (
        <div className="mt-4 p-3 bg-gray-50 border border-gray-200 rounded-lg">
          <div className="flex items-center space-x-2 mb-2">
            <Shield className="h-4 w-4 text-gray-600" />
            <h5 className="font-medium text-gray-800">Alert Summary</h5>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
            {['critical', 'high', 'medium', 'low'].map(severity => {
              const count = visibleAlerts.filter(alert => alert.severity === severity).length;
              if (count === 0) return null;
              
              const config = getSeverityConfig(severity);
              return (
                <div key={severity} className={`${config.bgColor} ${config.borderColor} border rounded px-2 py-1 text-center`}>
                  <span className={`font-medium ${config.textColor}`}>
                    {count} {getSeverityLabel(severity)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Safety disclaimer */}
      <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <div className="flex items-start space-x-2">
          <Shield className="h-4 w-4 text-blue-600 mt-0.5 flex-shrink-0" />
          <div>
            <h5 className="font-medium text-blue-800 text-sm">Clinical Safety Notice</h5>
            <p className="text-xs text-blue-700 mt-1">
              These alerts are generated by AI and should be used as decision support only. 
              Always correlate with clinical judgment and follow institutional protocols for emergency situations.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RedFlagAlerts;
