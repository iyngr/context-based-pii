# Build stage
FROM node:18-alpine as build
WORKDIR /app

# Define ARGs for build-time variables that are passed in from the cloudbuild.yaml
ARG REACT_APP_FIREBASE_API_KEY
ARG REACT_APP_FIREBASE_AUTH_DOMAIN
ARG REACT_APP_FIREBASE_PROJECT_ID
ARG REACT_APP_FIREBASE_STORAGE_BUCKET
ARG REACT_APP_FIREBASE_MESSAGING_SENDER_ID
ARG REACT_APP_FIREBASE_APP_ID

COPY package*.json ./
RUN npm ci
COPY . .

# The Create React App build script will automatically use the REACT_APP_* environment variables
# declared as ARGs above.
RUN npm run build

# Production stage
FROM node:18-alpine
WORKDIR /app

# Copy only necessary production dependencies and the server.js
COPY package*.json ./
RUN npm install --production

# Copy the server.js and the build output from the 'build' stage
COPY server.js .
COPY --from=build /app/build ./build

EXPOSE 8080
CMD ["node", "server.js"]