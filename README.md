# Cortexa

An intelligent test automation platform that leverages AI to streamline software testing workflows through automated test case generation, script creation, and comprehensive test management.

## 🚀 Features

### Core Capabilities
- **AI-Powered Test Generation**: Automatically generate comprehensive test cases from requirements and user stories
- **Smart Test Script Creation**: Convert test cases into executable test scripts for various frameworks
- **Interactive Chat Interface**: Natural language interaction for test planning and requirement analysis  
- **File Processing & OCR**: Extract and process content from documents and images
- **Use Case Management**: Organize and track testing scenarios and requirements
- **User Management**: Secure authentication and user role management

### Technical Features
- **Modern Web Interface**: React-based frontend with responsive design
- **RESTful API**: FastAPI backend with comprehensive endpoint coverage
- **Real-time Communication**: WebSocket support for live updates
- **File Upload & Processing**: Support for various document formats
- **Database Integration**: PostgreSQL with Alembic migrations
- **Cloud Storage**: AWS S3 and Azure Blob Storage integration

## 🏗️ Architecture

```
Cortexa/
├── frontend/          # React + TypeScript frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── pages/         # Application pages
│   │   └── context/       # State management
├── backend/           # FastAPI backend
│   ├── api/              # API endpoints
│   ├── models/           # Database models
│   ├── services/         # Business logic
│   └── core/             # Configuration
└── backend-spa/       # Extended backend services
```

## 🛠️ Technology Stack

### Frontend
- **React 18** with TypeScript
- **Tailwind CSS** for styling
- **Shadcn/ui** component library
- **React Hook Form** for form management
- **Vite** for build tooling

### Backend
- **FastAPI** (Python) REST API
- **SQLAlchemy** ORM with PostgreSQL
- **Alembic** for database migrations
- **Pydantic** for data validation
- **JWT** authentication
- **WebSocket** support

### Infrastructure
- **Docker** containerization
- **PostgreSQL** database
- **AWS S3** / **Azure Blob** storage
- **Redis** for caching (optional)

## ⚙️ Prerequisites

- **Node.js** 18+ and npm/yarn
- **Python** 3.11+
- **PostgreSQL** 13+
- **Docker** (optional)

## 🚨 Important Notice

**This application requires proper environment configuration to function.**

The application will **not work** without the appropriate `.env` configuration files containing necessary API keys, database credentials, and service configurations.

**Need Help?** 

If you require access to this application or need assistance with setup, please contact:

📧 **[INSERT_CONTACT_EMAIL_HERE]**

## 🔧 Development Setup

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
# Configure your .env file with required variables
python main.py
```

### Database Setup
```bash
# Run migrations
cd backend
alembic upgrade head
```

## 📁 Key Directories

- `/frontend/src/components/` - Reusable UI components
- `/frontend/src/pages/` - Application pages and routing
- `/backend/api/v1/endpoints/` - API endpoint definitions
- `/backend/models/` - Database models and schemas
- `/backend/services/` - Business logic and external integrations
- `/backend/core/` - Configuration and utilities

## 🔐 Security

- Environment variables for sensitive configuration
- JWT-based authentication
- Input validation and sanitization
- Secure file upload handling
- Database query protection

## 🤝 Contributing

This is a private project. For contribution guidelines and access requests, please contact the development team.

## 📄 License

Private/Proprietary - All rights reserved.

---

**Note**: This application integrates with external AI services for enhanced functionality. Proper credentials and configuration are required for full operation.

For technical support or questions, please reach out via email.
