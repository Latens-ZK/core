# Frontend Dockerfile
FROM node:18-alpine

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .

# Build Next.js app
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
