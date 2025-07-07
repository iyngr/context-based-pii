require('dotenv').config();
const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.PORT || 8080;
const BACKEND_SERVICE_URL = process.env.BACKEND_SERVICE_URL || 'http://localhost:8081'; // Default for local development

// Middleware to set security headers for Firebase Authentication
app.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin-allow-popups');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    next();
});

// Serve static files from the React build directory
app.use(express.static(path.join(__dirname, 'build')));

// Proxy API requests to the backend service
app.use('/api', createProxyMiddleware({
    target: BACKEND_SERVICE_URL,
    changeOrigin: true,
    pathRewrite: {
        '^/api': '', // remove /api prefix when forwarding to backend
    },
    timeout: 300000, // 5 minutes timeout
    onProxyReq: (proxyReq, req, res) => {
        // Log the proxy request details
        console.log(`Proxying request: ${req.method} ${req.url} -> ${proxyReq.protocol}//${proxyReq.host}${proxyReq.path}`);
    },
    onError: (err, req, res) => {
        console.error('Proxy error:', err);
        res.status(500).send('Proxy error');
    }
}));

// All other requests are served by the React app
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'build', 'index.html'));
});

app.listen(PORT, () => {
    console.log(`Frontend proxy server listening on port ${PORT}`);
    console.log(`Proxying backend requests to: ${BACKEND_SERVICE_URL}`);
});