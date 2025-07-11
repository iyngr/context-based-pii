import React, { useState, useEffect, useRef } from 'react';
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
import { getAuth } from "firebase/auth"; // Import Firebase auth
import { v4 as uuidv4 } from 'uuid'; // Import uuid

const ChatSimulator = ({ setView, setJobId }) => {
    const [messages, setMessages] = useState([]);
    const [customerInput, setCustomerInput] = useState('');
    const [agentInput, setAgentInput] = useState('');
    const conversationIdRef = useRef(null);

    useEffect(() => {
        // Generate a unique conversation ID when the component mounts
        if (!conversationIdRef.current) {
            conversationIdRef.current = uuidv4();
        }
    }, []);

    const handleSendMessage = async (speaker, text) => {
        if (text.trim() === '') return;
        const role = speaker === 'Customer' ? 'END_USER' : 'AGENT';
        const originalMessage = { speaker: role, text };

        // Add original message to the display immediately
        setMessages(prevMessages => [...prevMessages, originalMessage]);

        if (speaker === 'Customer') {
            setCustomerInput('');
        } else {
            setAgentInput('');
        }

        try {
            const auth = getAuth();
            if (!auth.currentUser) {
                throw new Error("User not authenticated.");
            }
            const idToken = await auth.currentUser.getIdToken(true);

            if (role === 'AGENT') {
                // Agent utterance: call handle-agent-utterance and get redacted text
                const response = await fetch(`/api/handle-agent-utterance`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${idToken}`,
                    },
                    body: JSON.stringify({
                        conversation_id: conversationIdRef.current,
                        transcript: text,
                    }),
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                const redactedMessage = { speaker: role, text: data.redacted_transcript };

                // Replace the last message (the original one) with the redacted version
                setMessages(prevMessages => {
                    const newMessages = [...prevMessages];
                    newMessages[newMessages.length - 1] = redactedMessage;
                    return newMessages;
                });
            } else {
                // Customer utterance: call real-time redaction
                const response = await fetch(`/api/redact-utterance-realtime`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${idToken}`,
                    },
                    body: JSON.stringify({
                        conversation_id: conversationIdRef.current,
                        utterance: text,
                    }),
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                const redactedMessage = { speaker: role, text: data.redacted_utterance };

                // Replace the last message (the original one) with the redacted version
                setMessages(prevMessages => {
                    const newMessages = [...prevMessages];
                    newMessages[newMessages.length - 1] = redactedMessage;
                    return newMessages;
                });
            }
        } catch (error) {
            console.error('Error processing utterance:', error);
            // Optionally, show an error to the user or handle it gracefully
        }
    };

    const handleAnalyze = async () => {
        try {
            const auth = getAuth();
            if (!auth.currentUser) {
                throw new Error("User not authenticated.");
            }
            const idToken = await auth.currentUser.getIdToken(true); // Get fresh token

            const response = await fetch(`/api/initiate-redaction`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${idToken}`,
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
                                    msg.speaker === 'END_USER' ? 'flex-start' : 'flex-end',
                            }}
                        >
                            <Box
                                sx={{
                                    bgcolor:
                                        msg.speaker === 'END_USER' ? '#f0f0f0' : 'primary.main',
                                    color: msg.speaker === 'END_USER' ? 'black' : 'white',
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