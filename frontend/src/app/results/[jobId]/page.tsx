'use client';

import React, { useState, useEffect } from 'react';
import { getAuth, onAuthStateChanged, User } from "firebase/auth";
import { CircularProgress, Box } from '@mui/material';
import ResultsView from '../../../components/ResultsView';
import LoginScreen from '../../../components/LoginScreen';
import app from '../../../firebase-config';
import { useRouter, useParams } from 'next/navigation';

export default function ResultsPage() {
    const [user, setUser] = useState<User | null>(null);
    const [idToken, setIdToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();
    const params = useParams();
    const jobId = params.jobId as string;

    useEffect(() => {
        const auth = getAuth(app);
        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);
            if (currentUser) {
                try {
                    const token = await currentUser.getIdToken();
                    setIdToken(token);
                } catch (error) {
                    console.error("Error getting ID token:", error);
                    setIdToken(null);
                }
            } else {
                setIdToken(null);
            }
            setLoading(false);
        });

        return () => unsubscribe();
    }, []);

    const handleSetView = (view: string) => {
        if (view === 'welcome') {
            router.push('/');
        } else if (view === 'chat') {
            router.push('/chat');
        } else if (view === 'upload') {
            router.push('/upload');
        }
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
            <ResultsView 
                jobId={jobId} 
                setView={handleSetView} 
                idToken={idToken} 
            />
        </div>
    );
}