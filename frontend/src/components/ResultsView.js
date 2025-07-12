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

    const renderMessage = (originalSegment, redactedSegment, index, isOriginalPanel) => {
        // If both messages are missing at this index, render an empty placeholder to maintain alignment
        if (!originalSegment && !redactedSegment) {
            return <ListItem key={index} sx={{ minHeight: 50 }} />;
        }

        // Determine the canonical speaker for this index - use original first, then redacted
        // This ensures both panels use the same speaker for alignment at the same index
        const canonicalSpeaker = originalSegment?.speaker || redactedSegment?.speaker || 'UNKNOWN';

        // Get the message for the current panel
        const currentMessage = isOriginalPanel ? originalSegment : redactedSegment;
        const textToDisplay = currentMessage?.text || '';
        const hasMessage = !!currentMessage;

        return (
            <ListItem
                ref={el => {
                    if (isOriginalPanel) originalItemRefs.current[index] = el;
                    else redactedItemRefs.current[index] = el;
                }}
                key={index}
                sx={{
                    // Use canonical speaker for consistent alignment across both panels
                    justifyContent: canonicalSpeaker === 'END_USER' ? 'flex-start' : 'flex-end',
                    minHeight: 50, // Ensure a minimum height for all list items
                    opacity: hasMessage ? 1 : 0.3, // Dim entire item if no message for this panel
                }}
            >
                <Box
                    sx={{
                        bgcolor: isOriginalPanel
                            ? canonicalSpeaker === 'END_USER'
                                ? '#f0f0f0'  // Gray for original END_USER
                                : '#1976d2'  // Blue for original AGENT
                            : canonicalSpeaker === 'END_USER'
                                ? '#ffebee'  // Light red for redacted END_USER
                                : '#e8f5e8', // Light green for redacted AGENT
                        color: (isOriginalPanel && canonicalSpeaker === 'AGENT') ? 'white' : 'black',
                        p: 1,
                        borderRadius: 2,
                        maxWidth: '80%',
                        opacity: hasMessage ? 1 : 0.5, // Additional dimming for the message box
                        border: hasMessage ? 'none' : '1px dashed #ccc', // Dashed border for missing messages
                    }}
                >
                    <ListItemText
                        primary={
                            hasMessage ? (
                                <Typography
                                    dangerouslySetInnerHTML={{
                                        __html: isOriginalPanel
                                            ? textToDisplay
                                            : textToDisplay.replace(
                                                /\[(.*?)\]/g,
                                                '<span style="background-color: #ffeb3b; padding: 2px; border-radius: 3px;">[$1]</span>'
                                            ),
                                    }}
                                />
                            ) : (
                                <Typography
                                    sx={{
                                        fontStyle: 'italic',
                                        color: 'text.secondary',
                                        fontSize: '0.9em'
                                    }}
                                >
                                    [No message in {isOriginalPanel ? 'original' : 'redacted'} transcript]
                                </Typography>
                            )
                        }
                        secondary={canonicalSpeaker}
                    />
                </Box>
            </ListItem>
        );
    };

    useEffect(() => {
        if (status === 'DONE' && originalConversation && redactedConversation) {
            // Ensure refs are cleared and re-populated correctly
            originalItemRefs.current = [];
            redactedItemRefs.current = [];

            // Use a timeout to ensure elements are rendered before measuring
            setTimeout(() => {
                const maxLength = Math.max(
                    originalConversation.transcript.transcript_segments.length,
                    redactedConversation.transcript.transcript_segments.length
                );

                for (let i = 0; i < maxLength; i++) {
                    const originalEl = originalItemRefs.current[i];
                    const redactedEl = redactedItemRefs.current[i];

                    if (originalEl && redactedEl) {
                        const originalHeight = originalEl.offsetHeight;
                        const redactedHeight = redactedEl.offsetHeight;
                        const maxHeight = Math.max(originalHeight, redactedHeight);

                        originalEl.style.minHeight = `${maxHeight}px`;
                        redactedEl.style.minHeight = `${maxHeight}px`;
                    }
                }
            }, 100); // Small delay to allow DOM to update
        }
    }, [status, originalConversation, redactedConversation]);

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
                <Box sx={{ display: 'flex', flexDirection: 'row', gap: 2 }}>
                    <Box sx={{ flex: 1 }}>
                        <Typography variant="h6">Original Transcript</Typography>
                        <Paper
                            elevation={3}
                            sx={{ height: 500, overflowY: 'auto', p: 2 }}
                            ref={originalPanelRef}
                            onScroll={(e) => handleScroll(e.target)}
                        >
                            <List>
                                {Array.from({ length: Math.max(originalConversation.transcript.transcript_segments.length, redactedConversation.transcript.transcript_segments.length) }).map((_, index) => {
                                    const originalSegment = originalConversation.transcript.transcript_segments[index];
                                    const redactedSegment = redactedConversation.transcript.transcript_segments[index];
                                    return renderMessage(
                                        originalSegment,
                                        redactedSegment,
                                        index,
                                        true // This is the original panel
                                    );
                                })}
                            </List>
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
                            <List>
                                {Array.from({ length: Math.max(originalConversation.transcript.transcript_segments.length, redactedConversation.transcript.transcript_segments.length) }).map((_, index) => {
                                    const originalSegment = originalConversation.transcript.transcript_segments[index];
                                    const redactedSegment = redactedConversation.transcript.transcript_segments[index];
                                    return renderMessage(
                                        originalSegment,
                                        redactedSegment,
                                        index,
                                        false // This is the redacted panel
                                    );
                                })}
                            </List>
                        </Paper>
                    </Box>
                </Box>
            )}
        </Box>
    );
};

export default ResultsView;