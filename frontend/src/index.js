import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import app from './firebase-config';
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";

// Initialize Firebase Authentication
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

// Function to handle Google Sign-In
const handleGoogleSignIn = () => {
    signInWithPopup(auth, provider)
        .then((result) => {
            // This gives you a Google Access Token. You can use it to access the Google API.
            const credential = GoogleAuthProvider.credentialFromResult(result);
            const token = credential.accessToken;
            // The signed-in user info.
            const user = result.user;
            console.log("Google Sign-in Successful!", user);
            // ID Token will be handled by onAuthStateChanged in App.js
        })
        .catch((error) => {
            // Handle Errors here.
            const errorCode = error.code;
            const errorMessage = error.message;
            // The email of the user's account used.
            const email = error.customData ? error.customData.email : 'N/A';
            // The AuthCredential type that was used.
            const credential = GoogleAuthProvider.credentialFromError(error);
            console.error(`Google Sign-in Error: ${errorCode} - ${errorMessage}`, { email, credential });
        });
};

// Automatically trigger Google Sign-In when the app loads
// In a real application, you would likely have a button for this.
// For now, we'll just call it directly to ensure the flow is initiated.
handleGoogleSignIn();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);