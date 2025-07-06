import React, { useState, useEffect, useRef } from 'react';
import {
    Box,
    Typography,
    Paper,
    CircularProgress,
    Alert,
    Button,
    List,
    ListItem,
    ListItemText,
} from '@mui/material';

const ResultsView = ({ jobId, setView, idToken }) => {
    const [status, setStatus] = useState('PROCESSING');
    const [originalConversation, setOriginalConversation] = useState(null);
    const [redactedConversation, setRedactedConversation] = useState(null);
    const [error, setError] = useState(null);

    const originalPanelRef = useRef(null);
    const redactedPanelRef = useRef(null);
    const isScrolling = useRef(false);

    useEffect(() => {
        if (!jobId) return;

        const poll = setInterval(async () => {
            try {
                const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/redaction-status/${jobId}`, {
                    headers: {
                        'Authorization': `Bearer ${idToken}`,
                    },
                });
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();

                if (data.original_conversation) {
                    setOriginalConversation(data.original_conversation);
                }
                if (data.redacted_conversation) {
                    setRedactedConversation(data.redacted_conversation);
                }

                if (data.status === 'DONE') {
                    setStatus('DONE');
                    clearInterval(poll);
                } else if (data.status === 'FAILED') {
                    setStatus('FAILED');
                    setError('Processing failed. Please try again.');
                    clearInterval(poll);
                }
            } catch (err) {
                setStatus('FAILED');
                setError('An error occurred while fetching the results.');
                clearInterval(poll);
            }
        }, 3000);

        return () => clearInterval(poll);
    }, [jobId]);

    const handleScroll = (scrolledPanel) => {
        if (isScrolling.current) return;
        isScrolling.current = true;

        const { scrollTop } = scrolledPanel;
        if (scrolledPanel === originalPanelRef.current && redactedPanelRef.current) {
            redactedPanelRef.current.scrollTop = scrollTop;
        } else if (scrolledPanel === redactedPanelRef.current && originalPanelRef.current) {
            originalPanelRef.current.scrollTop = scrollTop;
        }

        setTimeout(() => {
            isScrolling.current = false;
        }, 50);
    };

    const renderTranscript = (segments, redacted = false) => (
        <List>
            {segments && segments.map((msg, index) => (
                <ListItem
                    key={index}
                    sx={{
                        justifyContent:
                            msg.speaker === 'END_USER' ? 'flex-start' : 'flex-end', // Changed 'CUSTOMER' to 'END_USER'
                    }}
                >
                    <Box
                        sx={{
                            bgcolor: redacted
                                ? msg.speaker === 'END_USER' // Changed 'CUSTOMER' to 'END_USER'
                                    ? '#fff0f0'
                                    : '#e0f7fa'
                                : msg.speaker === 'END_USER' // Changed 'CUSTOMER' to 'END_USER'
                                    ? '#f0f0f0'
                                    : 'primary.main',
                            color:
                                !redacted && msg.speaker === 'AGENT' ? 'white' : 'black',
                            p: 1,
                            borderRadius: 2,
                            maxWidth: '80%',
                        }}
                    >
                        <ListItemText
                            primary={
                                <Typography
                                    dangerouslySetInnerHTML={{
                                        __html: msg.text.replace(
                                            /\[(.*?)\]/g,
                                            '<span style="background-color: #ffeb3b; padding: 2px; border-radius: 3px;">[$1]</span>'
                                        ),
                                    }}
                                />
                            }
                            secondary={msg.speaker}
                        />
                    </Box>
                </ListItem>
            ))}
        </List>
    );

    return (
        <Box sx={{ margin: 'auto', mt: 4 }}> {/* Removed maxWidth */}
            <Button onClick={() => setView('welcome')} sx={{ mb: 2 }}>
                Start Over
            </Button>
            <Typography variant="h5" gutterBottom>
                Redaction Results
            </Typography>
            {status === 'PROCESSING' && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>
                        Analyzing conversation for PII...
                    </Typography>
                </Box>
            )}
            {status === 'FAILED' && (
                <Alert severity="error" sx={{ mt: 2 }}>
                    {error}
                </Alert>
            )}
            {status === 'DONE' && originalConversation && redactedConversation && (
                <Box sx={{ display: 'flex', flexDirection: 'row', gap: 2 }}>
                    <Box sx={{ flex: 1 }}>
                        <Typography variant="h6">Original Transcript</Typography>
                        <Paper
                            elevation={3}
                            sx={{ height: 500, overflowY: 'auto', p: 2 }}
                            ref={originalPanelRef}
                            onScroll={(e) => handleScroll(e.target)}
                        >
                            {renderTranscript(
                                originalConversation.transcript.transcript_segments,
                                false
                            )}
                        </Paper>
                    </Box>
                    <Box sx={{ flex: 1 }}>
                        <Typography variant="h6">Redacted Transcript</Typography>
                        <Paper
                            elevation={3}
                            sx={{ height: 500, overflowY: 'auto', p: 2 }}
                            ref={redactedPanelRef}
                            onScroll={(e) => handleScroll(e.target)}
                        >
                            {renderTranscript(
                                redactedConversation.transcript.transcript_segments,
                                true
                            )}
                        </Paper>
                    </Box>
                </Box>
            )}
        </Box>
    );
};

export default ResultsView;