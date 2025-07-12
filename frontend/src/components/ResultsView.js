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
    Grid, // Added Grid import
} from '@mui/material';

const ResultsView = ({ jobId, setView, idToken }) => {
    const [status, setStatus] = useState('PROCESSING');
    const [originalConversation, setOriginalConversation] = useState(null);
    const [redactedConversation, setRedactedConversation] = useState(null);
    const [error, setError] = useState(null);

    const originalPanelRef = useRef(null);
    const redactedPanelRef = useRef(null);
    const isScrolling = useRef(false);
    const originalItemRefs = useRef([]); // Added useRef for original items
    const redactedItemRefs = useRef([]); // Added useRef for redacted items

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

    const renderMessage = (msg, redacted = false) => {
        if (!msg) {
            return <Box sx={{ minHeight: 50 }} />; // Placeholder for alignment
        }

        return (
            <ListItem
                sx={{
                    justifyContent:
                        msg.speaker === 'END_USER' ? 'flex-start' : 'flex-end',
                }}
            >
                <Box
                    sx={{
                        bgcolor: redacted
                            ? msg.speaker === 'END_USER'
                                ? '#fff0f0'
                                : '#e0f7fa'
                            : msg.speaker === 'END_USER'
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
                                    __html: redacted
                                        ? msg.text.replace(
                                            /\[(.*?)\]/g,
                                            '<span style="background-color: #ffeb3b; padding: 2px; border-radius: 3px;">[$1]</span>'
                                        )
                                        : msg.text,
                                }}
                            />
                        }
                        secondary={msg.speaker}
                    />
                </Box>
            </ListItem>
        );
    };

    return (
        <Box sx={{ margin: 'auto', mt: 4 }}>
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
                <Grid container spacing={2}>
                    <Grid item xs={6}>
                        <Typography variant="h6">Original Transcript</Typography>
                        <Paper
                            elevation={3}
                            sx={{ height: 500, overflowY: 'auto', p: 2 }}
                            ref={originalPanelRef}
                            onScroll={(e) => handleScroll(e.target)}
                        >
                            <List>
                                {Array.from({ length: Math.max(originalConversation.transcript.transcript_segments.length, redactedConversation.transcript.transcript_segments.length) }).map((_, index) => (
                                    renderMessage(originalConversation.transcript.transcript_segments[index], false)
                                ))}
                            </List>
                        </Paper>
                    </Grid>
                    <Grid item xs={6}>
                        <Typography variant="h6">Redacted Transcript</Typography>
                        <Paper
                            elevation={3}
                            sx={{ height: 500, overflowY: 'auto', p: 2 }}
                            ref={redactedPanelRef}
                            onScroll={(e) => handleScroll(e.target)}
                        >
                            <List>
                                {Array.from({ length: Math.max(originalConversation.transcript.transcript_segments.length, redactedConversation.transcript.transcript_segments.length) }).map((_, index) => (
                                    renderMessage(redactedConversation.transcript.transcript_segments[index], true)
                                ))}
                            </List>
                        </Paper>
                    </Grid>
                </Grid>
            )}
        </Box>
    );
};

export default ResultsView;