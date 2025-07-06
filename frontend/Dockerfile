# Build stage
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Production stage
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --production
COPY . .
RUN npm run build

# Copy the server.js and the build output
COPY server.js .
COPY --from=build /app/build ./build

EXPOSE 8080
CMD ["node", "server.js"]