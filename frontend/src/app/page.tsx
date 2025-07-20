'use client';

import React, { useState, useEffect } from 'react';
import { Container, Typography, Button, Box, CircularProgress } from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import LoginScreen from '../components/LoginScreen';
import { getAuth, onAuthStateChanged, User } from "firebase/auth";
import app from '../firebase-config';
import '../App.css';
import { useRouter } from 'next/navigation';

function HomePage() {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        // Initialize Firebase
        const auth = getAuth(app);
        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);
            if (currentUser) {
                try {
                    const token = await currentUser.getIdToken();
                    console.log("Firebase ID Token obtained:", token);
                } catch (error) {
                    console.error("Error getting ID token:", error);
                }
            }
            setLoading(false);
        });

        // Cleanup subscription on unmount
        return () => unsubscribe();
    }, []);

    const handleLoginSuccess = () => {
        // This function can be used to trigger a re-render or state change if needed
        // The onAuthStateChanged listener will automatically handle the user state update
    };

    const WelcomeScreen = () => (
        <Container maxWidth="sm" sx={{ textAlign: 'center', mt: 8 }}>
            <Typography variant="h4" component="h1" gutterBottom>
                Context-Based PII Redaction
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
                Choose how you would like to test the redaction service.
            </Typography>
            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2 }}>
                <Button
                    variant="contained"
                    startIcon={<ChatIcon />}
                    onClick={() => router.push('/chat')}
                    size="large"
                >
                    Live Chat Simulation
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<UploadFileIcon />}
                    onClick={() => router.push('/upload')}
                    size="large"
                >
                    Upload Conversation
                </Button>
            </Box>
        </Container>
    );

    // While checking auth state, show a loader
    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                <CircularProgress />
            </Box>
        );
    }

    // If no user is logged in, show the LoginScreen
    if (!user) {
        return <LoginScreen onLoginSuccess={handleLoginSuccess} />;
    }

    // If user is logged in, show the main app
    return <div className="App"><WelcomeScreen /></div>;
}

export default HomePage;