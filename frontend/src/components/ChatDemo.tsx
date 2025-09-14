import React, { useState } from 'react';
import { MessageSquare, X } from 'lucide-react';
import ConversationChat from './ConversationChat';

const ChatDemo: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="fixed bottom-4 left-4 z-50">
      {!isOpen ? (
        <button
          onClick={() => setIsOpen(true)}
          className="w-14 h-14 bg-blue-500 hover:bg-blue-600 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center hover:scale-105"
        >
          <MessageSquare className="h-6 w-6" />
        </button>
      ) : (
        <div className="w-96 h-96 bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">
          <div className="bg-blue-500 text-white px-4 py-3 flex items-center justify-between">
            <h3 className="font-semibold">Chat Demo</h3>
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

export default ChatDemo;
