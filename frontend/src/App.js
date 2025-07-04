import React, { useState } from 'react';
import { Container, Typography, Button, Box } from '@mui/material';
import ChatIcon from '@mui/icons-material/Chat';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ChatSimulator from './components/ChatSimulator';
import UploadConversation from './components/UploadConversation';
import ResultsView from './components/ResultsView';
import './App.css';

function App() {
    const [view, setView] = useState('welcome');
    const [jobId, setJobId] = useState(null);

    const WelcomeScreen = () => (
        <Container maxWidth="sm" sx={{ textAlign: 'center', mt: 8 }}>
            <Typography variant="h4" component="h1" gutterBottom>
                CCAI PII Redaction Service
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
                return <ChatSimulator setView={setView} setJobId={setJobId} />;
            case 'upload':
                return <UploadConversation setView={setView} setJobId={setJobId} />;
            case 'results':
                return <ResultsView jobId={jobId} setView={setView} />;
            default:
                return <WelcomeScreen />;
        }
    };

    return <div className="App">{renderView()}</div>;
}

export default App;