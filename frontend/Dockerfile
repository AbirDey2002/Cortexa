# --- Stage 1: Build the Application ---
# Node Image to build the app
# Checked node -v version - 18.19.0
FROM node:18-alpine AS builder

# Set the working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm ci

# Add build arguments for VITE env vars
ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
ARG VITE_AUTH0_AUDIENCE
ARG VITE_BACKEND_URL

# Set them as environment variables during build
ENV VITE_AUTH0_DOMAIN=$VITE_AUTH0_DOMAIN
ENV VITE_AUTH0_CLIENT_ID=$VITE_AUTH0_CLIENT_ID
ENV VITE_AUTH0_AUDIENCE=$VITE_AUTH0_AUDIENCE
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL

# Copy the rest of the application code
COPY . .

# Build the application
# (Verify your build script in package.json is named "build")
RUN npm run build

# --- Stage 2: Serve the Application ---
# Use Nginx to serve the static files
FROM nginx:alpine

# Copy the build output from the builder stage to Nginx's default html folder
# Note: React usually builds to /app/build, Vue/Vite to /app/dist.
# Check where your npm run build outputs files!
# since its vue, its /app/dist and if it was react, it would be /app/build
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose to port 80
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]