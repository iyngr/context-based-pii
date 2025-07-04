import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    Grid,
    CircularProgress,
    Alert,
    Button,
    List,
    ListItem,
    ListItemText,
} from '@mui/material';

const ResultsView = ({ jobId, setView }) => {
    const [status, setStatus] = useState('PROCESSING');
    const [conversation, setConversation] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!jobId) return;

        const poll = setInterval(async () => {
            try {
                const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/redaction-status/${jobId}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();

                if (data.status === 'DONE') {
                    setStatus('DONE');
                    setConversation(data.conversation);
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

    const renderTranscript = (segments, redacted = false) => (
        <List>
            {segments.map((msg, index) => (
                <ListItem
                    key={index}
                    sx={{
                        justifyContent:
                            msg.speaker === 'Customer' ? 'flex-start' : 'flex-end',
                    }}
                >
                    <Box
                        sx={{
                            bgcolor: redacted
                                ? msg.speaker === 'Customer'
                                    ? '#fff0f0'
                                    : '#e0f7fa'
                                : msg.speaker === 'Customer'
                                    ? '#f0f0f0'
                                    : 'primary.main',
                            color:
                                !redacted && msg.speaker === 'Agent' ? 'white' : 'black',
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
        <Box sx={{ maxWidth: 1200, margin: 'auto', mt: 4 }}>
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
            {status === 'DONE' && conversation && (
                <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                        <Typography variant="h6">Original Transcript</Typography>
                        <Paper elevation={3} sx={{ height: 500, overflowY: 'auto', p: 2 }}>
                            {renderTranscript(
                                conversation.transcript.transcript_segments,
                                false
                            )}
                        </Paper>
                    </Grid>
                    <Grid item xs={12} md={6}>
                        <Typography variant="h6">Redacted Transcript</Typography>
                        <Paper elevation={3} sx={{ height: 500, overflowY: 'auto', p: 2 }}>
                            {renderTranscript(
                                conversation.transcript.transcript_segments,
                                true
                            )}
                        </Paper>
                    </Grid>
                </Grid>
            )}
        </Box>
    );
};

export default ResultsView;