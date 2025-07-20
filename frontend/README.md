# Next.js Frontend for Context-Based PII Redaction

This is a [Next.js](https://nextjs.org) project that provides the frontend interface for the Context-Based PII redaction system. The application has been migrated from Create React App to Next.js with PNPM.

## Migration Summary

### What Changed
- **Framework**: Migrated from Create React App to Next.js 15.3.5
- **Package Manager**: Migrated from NPM to PNPM
- **Routing**: Converted from state-based routing to Next.js file-based routing
- **API Proxy**: Replaced Express proxy server with Next.js API routes
- **Environment Variables**: Updated from `REACT_APP_*` to `NEXT_PUBLIC_*` prefix
- **Build System**: Updated to use Next.js build system with standalone output

### What Stayed the Same
- **UI Framework**: Material-UI components and styling preserved
- **Authentication**: Firebase Authentication with Google Sign-In preserved
- **Functionality**: All original features maintained (Chat Simulator, Upload Conversation, Results View)
- **Component Logic**: Original React components preserved with minimal changes

## Getting Started

### Prerequisites
- Node.js 24+ 
- PNPM (installed automatically via corepack)

### Development Setup

1. Install dependencies:
```bash
pnpm install
```

2. Set up environment variables:
```bash
cp .env.local.example .env.local
# Edit .env.local with your Firebase configuration
```

3. Run the development server:
```bash
pnpm dev
```

4. Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Production Build

```bash
# Build the application
pnpm build

# Start the production server
pnpm start
```

## Project Structure

```
src/
├── app/                    # Next.js app directory
│   ├── page.tsx           # Home page (welcome screen)
│   ├── chat/              # Chat simulator page
│   ├── upload/            # Upload conversation page
│   ├── results/[jobId]/   # Results page with dynamic routing
│   ├── api/[...slug]/     # API proxy to backend services
│   ├── layout.tsx         # Root layout with Firebase initialization
│   └── globals.css        # Global styles
├── components/            # React components (preserved from original)
│   ├── ChatSimulator.js
│   ├── LoginScreen.js
│   ├── ResultsView.js
│   └── UploadConversation.js
├── firebase-config.js     # Firebase configuration
├── App.css               # Component styles
└── index.css             # Base styles
```

## Environment Variables

### Development
Create a `.env.local` file with the following variables:

```bash
NEXT_PUBLIC_FIREBASE_API_KEY=your_firebase_api_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project_id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id
BACKEND_SERVICE_URL=http://localhost:8081
```

### Production
Environment variables are injected at build time via Google Cloud Build from Secret Manager.

## Deployment

The application is deployed to Google Cloud Run using Docker. The deployment process:

1. **Build**: Cloud Build creates a Docker image with Next.js standalone output
2. **Environment**: Firebase config injected as build-time variables
3. **Runtime**: Backend service URL provided as runtime environment variable
4. **Scaling**: Auto-scales from 0 to 1 instances based on traffic

## API Routes

The `/api/[...slug]` route acts as a proxy to the backend services, forwarding requests to the configured `BACKEND_SERVICE_URL`.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial

## Migration Notes

### Breaking Changes
- URLs now use Next.js routing (e.g., `/chat`, `/upload`, `/results/[jobId]`)
- Environment variables must use `NEXT_PUBLIC_` prefix for client-side access
- Development server runs on port 3000 instead of port 8080

### Compatibility
- All Firebase authentication flows preserved
- Material-UI components work without changes
- API calls to backend services continue to work through the proxy
