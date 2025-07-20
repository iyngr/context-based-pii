import React from 'react';
import { getAuth, GoogleAuthProvider, signInWithPopup } from 'firebase/auth';
import { Button, Box, Typography, Paper } from '@mui/material';
import GoogleIcon from '@mui/icons-material/Google';

const LoginScreen = ({ onLoginSuccess }) => {
    const handleGoogleLogin = async () => {
        const auth = getAuth();
        const provider = new GoogleAuthProvider();
        try {
            await signInWithPopup(auth, provider);
            // The onAuthStateChanged listener in App.js will handle the redirect.
            onLoginSuccess();
        } catch (error) {
            console.error("Authentication failed:", error);
            // You can display an error message to the user here.
        }
    };

    return (
        <Box
            sx={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                backgroundColor: '#f5f5f5',
            }}
        >
            <Paper
                elevation={6}
                sx={{
                    padding: 4,
                    textAlign: 'center',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 2,
                }}
            >
                <Typography variant="h4" gutterBottom>
                    Welcome
                </Typography>
                <Typography variant="body1" color="textSecondary">
                    Please sign in to continue
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<GoogleIcon />}
                    onClick={handleGoogleLogin}
                    size="large"
                >
                    Sign in with Google
                </Button>
            </Paper>
        </Box>
    );
};

export default LoginScreen;
