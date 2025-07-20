'use client';

import React, { useState, useEffect } from 'react';
import { getAuth, onAuthStateChanged, User } from "firebase/auth";
import { CircularProgress, Box, Typography, Button } from '@mui/material';
import LoginScreen from '../../components/LoginScreen';
import app from '../../firebase-config';
import { useRouter } from 'next/navigation';

export default function ResultsIndexPage() {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        const auth = getAuth(app);
        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);
            setLoading(false);
        });

        return () => unsubscribe();
    }, []);

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                <CircularProgress />
            </Box>
        );
    }

    if (!user) {
        return <LoginScreen onLoginSuccess={() => { }} />;
    }

    return (
        <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            gap: 2
        }}>
            <Typography variant="h4" component="h1">
                Results
            </Typography>
            <Typography variant="body1" color="text.secondary">
                To view results, you need a specific job ID in the URL.
            </Typography>
            <Typography variant="body2" color="text.secondary">
                Example: /results/your-job-id-here
            </Typography>
            <Box sx={{ mt: 2 }}>
                <Button
                    variant="contained"
                    onClick={() => router.push('/')}
                    sx={{ mr: 1 }}
                >
                    Home
                </Button>
                <Button
                    variant="outlined"
                    onClick={() => router.push('/upload')}
                    sx={{ mr: 1 }}
                >
                    Upload Conversation
                </Button>
                <Button
                    variant="outlined"
                    onClick={() => router.push('/chat')}
                >
                    Chat Simulator
                </Button>
            </Box>
        </Box>
    );
}
