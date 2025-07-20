// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";

// Your web app's Firebase configuration
// These values will be injected via environment variables during the build process
// We trim each variable to remove any leading/trailing whitespace, such as newlines.
const firebaseConfig = {
    apiKey: process.env.REACT_APP_FIREBASE_API_KEY?.trim(),
    authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN?.trim(),
    projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID?.trim(),
    storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET?.trim(),
    messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID?.trim(),
    appId: process.env.REACT_APP_FIREBASE_APP_ID?.trim()
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

export default app;