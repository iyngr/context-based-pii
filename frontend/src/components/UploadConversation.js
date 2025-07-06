import React, { useState } from 'react';
import { Button, Box, Typography, Alert } from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';

const UploadConversation = ({ setView, setJobId, idToken }) => {
    const [error, setError] = useState(null);

    const handleFileChange = (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        if (file.type !== 'application/json') {
            setError('Invalid file type. Please upload a .json file.');
            return;
        }

        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const conversation = JSON.parse(e.target.result);
                try {
                    const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/initiate-redaction`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${idToken}`,
                        },
                        body: JSON.stringify({
                            transcript: {
                                transcript_segments: conversation.entries.map(entry => ({
                                    speaker: entry.role, // Map 'role' from uploaded JSON to 'speaker'
                                    text: entry.text,
                                    // You can add other fields from 'entry' here if needed by the backend,
                                    // e.g., original_entry_index: entry.original_entry_index,
                                    // user_id: entry.user_id,
                                }))
                            },
                        }),
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const data = await response.json();
                    setJobId(data.jobId); // Assuming the backend returns { jobId: '...' }
                    setView('results');
                } catch (err) {
                    console.error('Error uploading conversation:', err);
                    setError('Failed to upload conversation. Please try again.');
                }
            } catch (err) {
                setError('Invalid JSON format in the uploaded file.');
            }
        };
        reader.readAsText(file);
    };

    return (
        <Box sx={{ maxWidth: 800, margin: 'auto', mt: 4, textAlign: 'center' }}>
            <Button onClick={() => setView('welcome')} sx={{ mb: 2 }}>
                Back
            </Button>
            <Typography variant="h5" gutterBottom>
                Upload Existing Conversation
            </Typography>
            <Button
                variant="contained"
                component="label"
                startIcon={<UploadFileIcon />}
                size="large"
            >
                Select JSON File
                <input type="file" hidden accept=".json" onChange={handleFileChange} />
            </Button>
            {error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                    {error}
                </Alert>
            )}
        </Box>
    );
};

export default UploadConversation;