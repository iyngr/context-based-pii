'use client';

import React, { useState, useEffect } from 'react';
import { getAuth, onAuthStateChanged, User } from "firebase/auth";
import { CircularProgress, Box } from '@mui/material';
import UploadConversation from '../../components/UploadConversation';
import LoginScreen from '../../components/LoginScreen';
import app from '../../firebase-config';
import { useRouter } from 'next/navigation';

export default function UploadPage() {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        const auth = getAuth(app);
        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);
            if (currentUser) {
                try {
                    await currentUser.getIdToken();
                } catch (error) {
                    console.error("Error getting ID token:", error);
                }
            }
            setLoading(false);
        });

        return () => unsubscribe();
    }, []);

    const handleSetView = (view: string) => {
        if (view === 'welcome') {
            router.push('/');
        } else if (view === 'results') {
            router.push('/results');
        }
    };

    const handleSetJobId = (jobId: string) => {
        // Store jobId in localStorage for the results page
        localStorage.setItem('currentJobId', jobId);
        router.push(`/results/${jobId}`);
    };

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                <CircularProgress />
            </Box>
        );
    }

    if (!user) {
        return <LoginScreen onLoginSuccess={() => {}} />;
    }

    return (
        <div className="App">
            <UploadConversation 
                setView={handleSetView} 
                setJobId={handleSetJobId} 
            />
        </div>
    );
}