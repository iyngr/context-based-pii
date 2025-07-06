import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import app from './firebase-config';
import { getAuth, signInAnonymously } from "firebase/auth";

// Initialize Firebase Authentication
const auth = getAuth(app);
signInAnonymously(auth)
    .then(() => {
        // Signed in
        console.log("Firebase Anonymous Sign-in Successful!");
    })
    .catch((error) => {
        const errorCode = error.code;
        const errorMessage = error.message;
        console.error(`Firebase Anonymous Sign-in Error: ${errorCode} - ${errorMessage}`);
    });

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);