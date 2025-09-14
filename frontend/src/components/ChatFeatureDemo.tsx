import React, { useState } from 'react';
import { MessageSquare, X, Phone } from 'lucide-react';
import ConversationChat from './ConversationChat';

const ChatFeatureDemo: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="fixed bottom-4 left-4 z-50">
      {!isOpen ? (
        <button
          onClick={() => setIsOpen(true)}
          className="w-16 h-16 bg-gradient-to-br from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center hover:scale-105"
        >
          <MessageSquare className="h-7 w-7" />
        </button>
      ) : (
        <div className="w-96 h-[500px] bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">
          <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-4 py-3 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Phone className="h-4 w-4" />
              <h3 className="font-semibold">Doctor-Patient Chat</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-blue-600 rounded-full transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <ConversationChat caseId="demo-case" className="h-full" />
        </div>
      )}
    </div>
  );
};

export default ChatFeatureDemo;
