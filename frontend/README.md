# Clinical AI Assistant Frontend

A modern, responsive React frontend for the Clinical AI Assistant system, featuring explainable AI, multimodal input, and doctor-centric UX design.

## 🚀 Features

### Core Functionality
- **Multimodal Input**: Text, voice, and medical imaging support
- **Explainable AI**: Transparent reasoning chains and confidence scores
- **Differential Diagnosis**: Structured top-3 diagnosis with risk factors
- **Clinical Workflow**: EHR integration mockups and report generation
- **Safety Guardrails**: Bias detection and patient safety alerts
- **Knowledge Base**: Clinical vs Research mode toggle

### Modern UI/UX
- **Glassmorphism Design**: Modern translucent cards with backdrop blur
- **Smooth Animations**: Framer Motion powered transitions
- **Responsive Layout**: Mobile-first design approach
- **Accessibility**: WCAG compliant components
- **Dark/Light Mode**: Adaptive color schemes
- **Voice Integration**: Real-time voice recording and transcription

## 🛠️ Technology Stack

- **React 18** with TypeScript
- **Tailwind CSS** for styling
- **Framer Motion** for animations
- **React Hot Toast** for notifications
- **React Dropzone** for file uploads
- **Lucide React** for icons
- **Axios** for API communication

## 📦 Installation

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Set environment variables**:
   ```bash
   cp .env.example .env.local
   ```
   
   Configure your API endpoint:
   ```env
   REACT_APP_API_URL=http://localhost:8000
   ```

3. **Start development server**:
   ```bash
   npm start
   ```

4. **Build for production**:
   ```bash
   npm run build
   ```

## 🏗️ Project Structure

```
src/
├── components/           # React components
│   ├── ClinicalInterface.tsx    # Main interface
│   ├── XAIExplanation.tsx       # Explainable AI display
│   ├── DifferentialDiagnosis.tsx # Diagnosis results
│   ├── RedFlagAlerts.tsx        # Safety alerts
│   ├── ClinicalReportView.tsx   # Report viewer
│   ├── EHRIntegration.tsx       # EHR mockups
│   ├── KnowledgeBaseToggle.tsx  # Mode switching
│   ├── VoiceRecorder.tsx        # Voice input
│   └── PatientForm.tsx          # Patient data form
├── services/            # API services
│   └── api.ts          # API client and types
├── types/              # TypeScript definitions
│   └── index.ts        # Core type definitions
├── App.tsx             # Main app component
├── index.tsx           # App entry point
└── index.css           # Global styles
```

## 🎨 Design System

### Color Palette
- **Primary**: Medical Blue (#2563eb)
- **Secondary**: Deep Blue (#1e40af)
- **Success**: Green (#10b981)
- **Warning**: Amber (#f59e0b)
- **Danger**: Red (#ef4444)
- **Info**: Cyan (#06b6d4)

### Typography
- **Font**: Inter (Google Fonts)
- **Weights**: 300, 400, 500, 600, 700

### Components
- **Cards**: Glassmorphism with backdrop blur
- **Buttons**: Gradient backgrounds with hover effects
- **Inputs**: Modern rounded fields with focus states
- **Alerts**: Color-coded with gradient backgrounds

## 🔌 API Integration

The frontend is designed to work with the backend API endpoints:

### Current Endpoints
- `GET /health` - Health check
- `POST /infer` - Text-based inference
- `POST /image_infer` - Image analysis
- `POST /multimodal_infer` - Combined text and image

### Future Endpoints (Ready for Implementation)
- `POST /quick_entry` - Structured input
- `POST /ehr/import_patient` - EHR integration
- `GET /ehr/export_report` - Report export
- `GET /knowledge_base/mode` - Knowledge base status
- `POST /voice/transcribe` - Voice processing

## 🎯 Key Components

### ClinicalInterface
Main application interface with:
- Patient information form
- Multimodal input (text, voice, images)
- Quick entry dropdowns
- Analysis results display

### XAIExplanation
Explainable AI component featuring:
- Reasoning chain visualization
- Confidence breakdown by source
- Source attribution with relevance scores
- Evidence quality indicators

### DifferentialDiagnosis
Structured diagnosis display with:
- Top 3 ranked conditions
- Probability and confidence scores
- Risk factors and supporting evidence
- Red flag identification

### RedFlagAlerts
Safety alert system with:
- Severity-based color coding
- Dismissible alerts
- Action recommendations
- Clinical safety notices

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ and npm
- Backend server running on port 8000

### Installation
1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Configure environment** (optional):
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your backend URL
   ```

3. **Start the frontend**:
   ```bash
   npm start
   ```

4. **Open** http://localhost:3000

### Backend Integration
See [BACKEND_INTEGRATION.md](./BACKEND_INTEGRATION.md) for detailed integration instructions.

## 📱 Responsive Design

The interface is fully responsive with breakpoints:
- **Mobile**: < 640px
- **Tablet**: 640px - 1024px
- **Desktop**: > 1024px

## ♿ Accessibility

- WCAG 2.1 AA compliant
- Keyboard navigation support
- Screen reader friendly
- High contrast mode support
- Focus indicators

## 🔧 Development

### Available Scripts
- `npm start` - Development server
- `npm build` - Production build
- `npm test` - Run tests
- `npm eject` - Eject from Create React App

### Code Style
- ESLint configuration included
- Prettier formatting
- TypeScript strict mode
- Component-based architecture

## 🚀 Deployment

### Build for Production
```bash
npm run build
```

### Deploy to Static Hosting
The build folder contains static files ready for deployment to:
- Vercel
- Netlify
- AWS S3
- GitHub Pages

## 🔮 Future Enhancements

- **Real-time Collaboration**: Multi-user sessions
- **Advanced Analytics**: Usage tracking and insights
- **Mobile App**: React Native version
- **Offline Support**: PWA capabilities
- **AI Chat**: Conversational interface
- **Integration APIs**: Real EHR connections

## 📄 License

This project is part of the Clinical AI Assistant system developed for HopHacks 2025.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📞 Support

For questions or issues, please contact the development team or create an issue in the repository.
