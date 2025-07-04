import React, { useState } from 'react';
import {
    Box,
    TextField,
    Button,
    Paper,
    Typography,
    List,
    ListItem,
    ListItemText,
    Divider,
} from '@mui/material';

const ChatSimulator = ({ setView, setJobId }) => {
    const [messages, setMessages] = useState([]);
    const [customerInput, setCustomerInput] = useState('');
    const [agentInput, setAgentInput] = useState('');

    const handleSendMessage = (speaker, text) => {
        if (text.trim() === '') return;
        setMessages([...messages, { speaker, text }]);
        if (speaker === 'Customer') {
            setCustomerInput('');
        } else {
            setAgentInput('');
        }
    };

    const handleAnalyze = async () => {
        try {
            const response = await fetch('/initiate-redaction', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    transcript: { transcript_segments: messages },
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setJobId(data.jobId); // Assuming the backend returns { jobId: '...' }
            setView('results');
        } catch (error) {
            console.error('Error analyzing conversation:', error);
            alert('Failed to analyze conversation. Please try again.');
        }
    };

    return (
        <Box sx={{ maxWidth: 800, margin: 'auto', mt: 4 }}>
            <Button onClick={() => setView('welcome')} sx={{ mb: 2 }}>
                Back
            </Button>
            <Typography variant="h5" gutterBottom>
                Live Chat Simulation
            </Typography>
            <Paper
                elevation={3}
                sx={{ height: 400, overflowY: 'auto', p: 2, mb: 2 }}
            >
                <List>
                    {messages.map((msg, index) => (
                        <ListItem
                            key={index}
                            sx={{
                                justifyContent:
                                    msg.speaker === 'Customer' ? 'flex-start' : 'flex-end',
                            }}
                        >
                            <Box
                                sx={{
                                    bgcolor:
                                        msg.speaker === 'Customer' ? '#f0f0f0' : 'primary.main',
                                    color: msg.speaker === 'Customer' ? 'black' : 'white',
                                    p: 1,
                                    borderRadius: 2,
                                    maxWidth: '70%',
                                }}
                            >
                                <ListItemText primary={msg.text} secondary={msg.speaker} />
                            </Box>
                        </ListItem>
                    ))}
                </List>
            </Paper>
            <Divider sx={{ mb: 2 }} />
            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <TextField
                    label="Customer Input"
                    variant="outlined"
                    fullWidth
                    value={customerInput}
                    onChange={(e) => setCustomerInput(e.target.value)}
                    onKeyPress={(e) =>
                        e.key === 'Enter' && handleSendMessage('Customer', customerInput)
                    }
                />
                <Button
                    variant="contained"
                    onClick={() => handleSendMessage('Customer', customerInput)}
                >
                    Send
                </Button>
            </Box>
            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <TextField
                    label="Agent Input"
                    variant="outlined"
                    fullWidth
                    value={agentInput}
                    onChange={(e) => setAgentInput(e.target.value)}
                    onKeyPress={(e) =>
                        e.key === 'Enter' && handleSendMessage('Agent', agentInput)
                    }
                />
                <Button
                    variant="contained"
                    onClick={() => handleSendMessage('Agent', agentInput)}
                >
                    Send
                </Button>
            </Box>
            <Button
                variant="contained"
                color="secondary"
                onClick={handleAnalyze}
                disabled={messages.length === 0}
                fullWidth
                size="large"
            >
                Analyze Conversation
            </Button>
        </Box>
    );
};

export default ChatSimulator;