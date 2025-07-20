# Frontend Migration Changes Summary

## Overview
Migrated frontend from Create React App with custom Express server to standard Next.js architecture.

## Key Changes Made

### 1. **Removed Express Server Dependency**
- The `frontend-backup/server.js` file with Express proxy middleware is **no longer needed**
- Next.js handles routing and API proxying natively

### 2. **Updated Environment Variable Names**
Changed from Create React App conventions to Next.js conventions:

**Before (Create React App):**
- `REACT_APP_BACKEND_URL`
- `REACT_APP_TRANSCRIPT_AGGREGATOR_URL`
- `BACKEND_SERVICE_URL` (server-side only)

**After (Next.js):**
- `NEXT_PUBLIC_BACKEND_URL` (client-side accessible)
- `NEXT_PUBLIC_TRANSCRIPT_AGGREGATOR_URL` (client-side accessible)
- `BACKEND_SERVICE_URL` (server-side only, for API routes)

### 3. **Files Modified**

#### `frontend/next.config.ts`
- Updated to map `NEXT_PUBLIC_BACKEND_URL` to `BACKEND_SERVICE_URL` for API routes
- Maintains existing CORS headers configuration

#### `frontend/src/app/api/[...slug]/route.ts`
- Updated to read from both `BACKEND_SERVICE_URL` and `NEXT_PUBLIC_BACKEND_URL`
- This API route handles all `/api/*` requests and proxies them to backend services

#### `frontend/src/components/ResultsView.js`
- Updated environment variable references:
  - `REACT_APP_TRANSCRIPT_AGGREGATOR_URL` → `NEXT_PUBLIC_TRANSCRIPT_AGGREGATOR_URL`
  - `REACT_APP_BACKEND_URL` → `NEXT_PUBLIC_BACKEND_URL`

#### `frontend/Dockerfile`
- Added `NEXT_PUBLIC_BACKEND_URL` and `NEXT_PUBLIC_TRANSCRIPT_AGGREGATOR_URL` as build arguments
- Removed old `BACKEND_SERVICE_URL` build arg (now handled differently)

#### `frontend/cloudbuild.yaml`
- Updated build arguments to use `NEXT_PUBLIC_*` naming convention
- Added `TRANSCRIPT_AGGREGATOR_URL` secret mapping
- Updated Docker build args to match new environment variable names

### 4. **API Routing Strategy**
The frontend now uses Next.js API routes instead of Express middleware:

- **Frontend components** make requests to `/api/*` endpoints
- **Next.js API route** (`/src/app/api/[...slug]/route.ts`) proxies these to backend services
- **Environment variables** control which backend URLs are used

### 5. **Local Development**
For local development, your `.env.local` file should contain:
```env
NEXT_PUBLIC_FIREBASE_API_KEY=your_key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_domain
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_bucket
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id
NEXT_PUBLIC_BACKEND_URL=https://your-backend-url
NEXT_PUBLIC_TRANSCRIPT_AGGREGATOR_URL=https://your-aggregator-url
```

### 6. **Production Deployment**
- Cloud Build now passes environment variables as build arguments to Docker
- Next.js embeds `NEXT_PUBLIC_*` variables at build time
- API routes use `BACKEND_SERVICE_URL` from Cloud Run environment at runtime

## Benefits of This Migration

1. **Standard Next.js Architecture** - No custom Express server needed
2. **Better Environment Variable Handling** - Clear separation between client-side and server-side variables
3. **Improved Build Process** - Leverages Next.js optimization capabilities
4. **Easier Maintenance** - Standard Next.js patterns for API proxying
5. **Better Performance** - Next.js optimizations for static generation and server-side rendering

## Files That Can Be Removed

- `frontend-backup/server.js` - No longer needed with Next.js API routes
- Any Express.js dependencies in package.json (if they were added specifically for the custom server)

## Testing

To test these changes:
1. Set up your `.env.local` file with the correct environment variables
2. Run `pnpm dev` from the `frontend` directory
3. Test API calls through the `/api/*` endpoints
4. Verify that environment variables are correctly passed to components
