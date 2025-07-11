import React, { useState, useEffect } from 'react';
import { Container, Typography, Button, Box, CircularProgress } from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ChatSimulator from './components/ChatSimulator';
import UploadConversation from './components/UploadConversation';
import ResultsView from './components/ResultsView';
import LoginScreen from './components/LoginScreen'; // Import the new LoginScreen
import './App.css';
import { getAuth, onAuthStateChanged } from "firebase/auth";

function App() {
    const [view, setView] = useState('welcome');
    const [jobId, setJobId] = useState(null);
    const [user, setUser] = useState(null); // State to hold the user object
    const [idToken, setIdToken] = useState(null); // State to hold the Firebase ID token
    const [loading, setLoading] = useState(true); // State to handle initial auth check

    useEffect(() => {
        const auth = getAuth();
        const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
            setUser(currentUser);
            if (currentUser) {
                try {
                    const token = await currentUser.getIdToken();
                    setIdToken(token);
                    console.log("Firebase ID Token obtained:", token);
                } catch (error) {
                    console.error("Error getting ID token:", error);
                    setIdToken(null);
                }
            } else {
                setIdToken(null);
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
                    onClick={() => setView('chat')}
                    size="large"
                >
                    Live Chat Simulation
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<UploadFileIcon />}
                    onClick={() => setView('upload')}
                    size="large"
                >
                    Upload Conversation
                </Button>
            </Box>
        </Container>
    );

    const renderView = () => {
        switch (view) {
            case 'chat':
                return <ChatSimulator setView={setView} setJobId={setJobId} idToken={idToken} />;
            case 'upload':
                return <UploadConversation setView={setView} setJobId={setJobId} idToken={idToken} />;
            case 'results':
                return <ResultsView jobId={jobId} setView={setView} idToken={idToken} />;
            default:
                return <WelcomeScreen />;
        }
    };

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
    return <div className="App">{renderView()}</div>;
}

export default App;