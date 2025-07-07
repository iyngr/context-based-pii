# Build stage
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
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