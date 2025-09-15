hljs.highlightAll();

var clipboard = new ClipboardJS('#copy-button', {
    text: function() {
        return document.getElementById('content').textContent;
    }
});

clipboard.on('success', function(e) {
    e.clearSelection();
    openCopyNotice();
});

clipboard.on('error', function(e) {
    console.error('Copy failed:', e);
});

function generateCode() {
    // Display "Working on..." with a typing effect
    var contentElement = document.getElementById('content');
    contentElement.classList.add('typing');
    contentElement.textContent = 'Working on...';

    // Add a subtle pulse animation to the generate button to show it's working
    var generateBtn = document.querySelector('.generate');
    if (generateBtn) {
        generateBtn.style.animation = 'pulse 1s infinite';
        generateBtn.disabled = true;
    }

    // Set a 3-second delay before making the XHR request
    setTimeout(function() {
        // After 3 seconds, remove the typing effect and proceed with the XHR request
        contentElement.classList.remove('typing');

        var xhr = new XMLHttpRequest();
        xhr.open("GET", "/get_js_content", true);
        xhr.onreadystatechange = function () {
            if (xhr.readyState == 4 && xhr.status == 200) {
                // Update the code box with the new content
                contentElement.textContent = xhr.responseText;
                document.getElementById("code-box").style.display = "block";

                // Reset button state
                if (generateBtn) {
                    generateBtn.style.animation = '';
                    generateBtn.disabled = false;
                }

                // Generate AI responses sequentially - encouragement first, then suggestions
                generateAIResponsesSequentially();
            } else if (xhr.readyState == 4 && xhr.status === 400) {
                // No image uploaded for this session
                contentElement.textContent = 'Please upload or capture an image first.';
                document.getElementById("code-box").style.display = "block";
                
                // Reset button state
                if (generateBtn) {
                    generateBtn.style.animation = '';
                    generateBtn.disabled = false;
                }
            }
        };
        xhr.send();
    }, 3000); // 3000 milliseconds = 3 seconds
}

// Sequential generation approach - encouragement first, then suggestions
async function generateAIResponsesSequentially() {
    try {
        // Generate encouragement with streaming (word by word)
        await generateStreamingEncouragement();
        
        // Then generate idea with streaming (word by word)
        await generateStreamingIdea();
        
    } catch (e) {
        console.error('AI generation failed:', e);
        // Show fallback messages
        showEncouragement("Fantastic work! You're building your programming skills and doing amazing!");
        showSuggestions({
            idea: "Try adding some sound or light effects when an event happens!",
            blocks: ["ON BUTTON A", "SHOW ICON", "PLAY SOUND"]
        });
    }
}

// Generate streaming encouragement word by word
async function generateStreamingEncouragement() {
    try {
        const response = await fetch('/generate_encouragement_stream', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = '';
        let currentText = '';
        let hasStarted = false;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.word) {
                            // Show popup only when first word arrives
                            if (!hasStarted) {
                                openInlineEncouragement();
                                hasStarted = true;
                            }
                            
                            // Add word with proper spacing
                            currentText += data.word;
                            document.getElementById('inline-encouragement-text').innerHTML = 
                                `<h3>🎉 ${currentText}</h3>`;
                        }
                        
                        if (data.done) {
                            return; // Streaming complete
                        }
                    } catch (e) {
                        console.error('Error parsing streaming data:', e, 'Line:', line);
                    }
                }
            }
        }
    } catch (e) {
        console.error('Streaming encouragement failed:', e);
        // Fallback to regular encouragement
        showEncouragement("Fantastic work! You're building your programming skills and doing amazing!");
    }
}

// Generate streaming idea word by word
async function generateStreamingIdea() {
    try {
        const response = await fetch('/generate_idea_stream', { method: 'POST' });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = '';
        let currentText = '';
        let hasStarted = false;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.word) {
                            // Show popup only when first word arrives
                            if (!hasStarted) {
                                openSuggestion();
                                hasStarted = true;
                            }
                            
                            // Add word with proper spacing
                            currentText += data.word;
                            document.getElementById('suggestion-text').innerHTML = 
                                `<p><strong>💡 Idea to Try:</strong> ${currentText}</p>`;
                        }
                        
                        if (data.done) {
                            // Extract blocks from the idea text and show them
                            const blocks = extractBlocksFromIdea(currentText);
                            if (blocks.length > 0) {
                                const blocksHtml = blocks.map(block => `<li><code>${block}</code></li>`).join('');
                                document.getElementById('suggestion-text').innerHTML = 
                                    `<p><strong>💡 Idea to Try:</strong> ${currentText}</p>
                                     <p><strong>🧩 Blocks to Explore:</strong></p>
                                     <ul>${blocksHtml}</ul>`;
                            }
                            return; // Streaming complete
                        }
                    } catch (e) {
                        console.error('Error parsing streaming data:', e, 'Line:', line);
                    }
                }
            }
        }
    } catch (e) {
        console.error('Streaming idea failed:', e);
        // Fallback to regular suggestions
        showSuggestions({
            idea: "What if you added some sound effects when you press a button?",
            blocks: ["ON BUTTON A", "PLAY SOUND"]
        });
    }
}

// Extract block labels from idea text (parenthesized text)
function extractBlocksFromIdea(ideaText) {
    const blocks = [];
    const regex = /\(([^)]+)\)/g;
    let match;
    
    // Valid block patterns (all caps, no numbers, no quotes)
    const validBlockPattern = /^[A-Z\s]+$/;
    
    while ((match = regex.exec(ideaText)) !== null) {
        const block = match[1].trim();
        // Only include valid block names (all caps, no numbers, no quotes)
        if (validBlockPattern.test(block) && block.length > 2) {
            blocks.push(block);
        }
    }
    return blocks;
}

// Show encouragement with improved animation
function showEncouragement(encouragementText) {
    const formatted = `<h3>🎉 ${encouragementText}</h3>`;
    document.getElementById('inline-encouragement-text').innerHTML = formatted;
    openInlineEncouragement();
}



// Show suggestions with improved formatting
function showSuggestions(suggestions) {
    const formattedText = `
        <p><strong>💡 Idea to Try:</strong> ${suggestions.idea}</p>
        <p><strong>🧩 Blocks to Explore:</strong></p>
        <ul>
            ${suggestions.blocks.map(block => `<li><code>${block}</code></li>`).join('')}
        </ul>
    `;
    
    document.getElementById('suggestion-text').innerHTML = formattedText;
    openSuggestion();
}



// Webcam controls (lazy-open)
var video = document.getElementById('camera-feed');
var uploadedImage = document.getElementById('uploaded-image');
var cameraStream = null;

function openCamera() {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(function(stream) {
            cameraStream = stream;
            video.srcObject = stream;
            video.style.display = 'block';
            video.classList.remove('fade-in');
            void video.offsetWidth;
            video.classList.add('fade-in');
            var takeBtn = document.getElementById('take-picture-btn');
            if (takeBtn) {
                takeBtn.style.display = 'inline-flex';
                takeBtn.classList.remove('pop-bounce');
                void takeBtn.offsetWidth;
                takeBtn.classList.add('pop-bounce');
            }
            // Update toggle button text/state
            var ocb = document.getElementById('open-camera-btn');
            if (ocb) {
                ocb.innerHTML = '<i class="fas fa-video-slash"></i> Close Camera';
            }
        })
        .catch(function(err) {
            console.error("Error accessing the camera: ", err);
        });
}

function closeCamera() {
    // Animate out video and button first, then stop stream
    video.classList.remove('fade-in');
    void video.offsetWidth;
    video.classList.add('fade-out');
    var takeBtn = document.getElementById('take-picture-btn');
    if (takeBtn) {
        takeBtn.classList.remove('pop-bounce');
        void takeBtn.offsetWidth;
        takeBtn.classList.add('pop-out');
    }
    // After animations complete, actually hide and release srcObject
    setTimeout(function(){
        if (cameraStream) {
            cameraStream.getTracks().forEach(function(t){ t.stop(); });
            cameraStream = null;
        }
        video.srcObject = null;
        video.style.display = 'none';
        video.classList.remove('fade-out');
        if (takeBtn) {
            takeBtn.style.display = 'none';
            takeBtn.classList.remove('pop-out');
        }
        var ocb = document.getElementById('open-camera-btn');
        if (ocb) { ocb.innerHTML = '<i class="fas fa-camera"></i> Open Camera'; }
    }, 550);
}

function captureImage() {
    // Toggle behavior: open if closed, close if open
    if (!cameraStream) {
        openCamera();
    } else {
        closeCamera();
    }
}

function takePicture() {
    var videoEl = document.getElementById('camera-feed');
    if (!videoEl) { console.error('Video element not found!'); return; }

    var canvas = document.createElement('canvas');
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    canvas.getContext('2d').drawImage(videoEl, 0, 0, canvas.width, canvas.height);

    var dataURL = canvas.toDataURL('image/png');
    var uploadedImage = document.getElementById('uploaded-image');
    uploadedImage.src = dataURL;
    uploadedImage.style.display = 'block';
    document.getElementById('code-box').style.display = 'block';

    var blob = dataURItoBlob(dataURL);
    var filename = 'captured-image-' + Date.now() + '-' + Math.random().toString(36).substring(2) + '.png';
    var formData = new FormData();
    formData.append('file', blob, filename);

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/process_image_path', true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState == 4 && xhr.status == 200) {
            console.log('Image captured and processed successfully.');
        } else if (xhr.readyState == 4) {
            console.error('Error processing the captured image:', xhr.statusText);
        }
    };
    xhr.send(formData);
}

// Utility function to convert a dataURL to a Blob object
function dataURItoBlob(dataURI) {
    var byteString = atob(dataURI.split(',')[1]);
    var mimeString = dataURI.split(',')[0].split(':')[1].split(';')[0];
    var buffer = new ArrayBuffer(byteString.length);
    var dataArray = new Uint8Array(buffer);

    for (var i = 0; i < byteString.length; i++) {
        dataArray[i] = byteString.charCodeAt(i);
    }

    return new Blob([buffer], { type: mimeString });
}


function uploadImage() {
    var input = document.getElementById('image-input');
    var file = input.files[0];
    if (file) {
        var reader = new FileReader();
        reader.onload = function(e) {
            uploadedImage.src = e.target.result;
            uploadedImage.style.display = 'block';
            document.getElementById('code-box').style.display = 'block';
        };
        reader.readAsDataURL(file);

        var formData = new FormData();
        // Random filename for the captured image with datetime and unique identifier (rough) for avoiding conflicts
        var filename = 'uploaded-image-' + Date.now() + '-' + Math.random().toString(36).substring(2) + '.png';
        formData.append('file', file, filename);

        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/process_image_path', true);
        xhr.onreadystatechange = function() {
            if (xhr.readyState == 4 && xhr.status == 200) {
                console.log('File uploaded and processed');
            }
        };
        xhr.send(formData);
    }
}

function copyCode() {
    clipboard.onClick({ target: document.getElementById('copy-button') });
}

function downloadCode() {
    var code = document.getElementById('content').textContent;
    var blob = new Blob([code], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);

    var a = document.createElement('a');
    a.href = url;
    a.download = 'code.js';
    a.click();
    URL.revokeObjectURL(url);
}

// Suggestion modal controls
function openSuggestion() {
    var panel = document.getElementById('suggestion-panel');
    var card = document.getElementById('suggestion-card');
    if (!panel || !card) return;
    panel.classList.remove('hidden');
    // Force reflow so the next animation applies reliably
    void card.offsetWidth;
    card.classList.remove('slide-out-right');
    card.classList.add('slide-in-right');
}

function closeSuggestion() {
    var panel = document.getElementById('suggestion-panel');
    var card = document.getElementById('suggestion-card');
    if (!panel || !card) return;
    card.classList.remove('slide-in-right');
    // Force reflow to restart animation reliably
    void card.offsetWidth;
    card.classList.add('slide-out-right');
    setTimeout(function(){ panel.classList.add('hidden'); }, 380);
}

// Inline encouragement controls
function openInlineEncouragement() {
    var encouragement = document.getElementById('inline-encouragement');
    var codeBox = document.getElementById('code-box');
    if (!encouragement || !codeBox) return;
    
    // Show the encouragement card
    encouragement.classList.remove('hidden');
    encouragement.classList.add('visible');
    
    // Add class to code box to make it smaller and move left
    codeBox.classList.add('with-encouragement');
}

function closeInlineEncouragement() {
    var encouragement = document.getElementById('inline-encouragement');
    var codeBox = document.getElementById('code-box');
    if (!encouragement || !codeBox) return;
    
    // Start slide-out animation
    encouragement.classList.remove('visible');
    encouragement.classList.add('slide-out-right');
    
    // Remove class from code box to make it full width again (no delay needed with absolute positioning)
    codeBox.classList.remove('with-encouragement');
    
    // After animation completes, hide the element
    setTimeout(function() {
        encouragement.classList.remove('slide-out-right');
        encouragement.classList.add('hidden');
    }, 600); // Match the animation duration (0.6s)
}


// Copy notice panel controls
function openCopyNotice() {
    var overlay = document.getElementById('copy-overlay');
    var card = document.getElementById('copy-card');
    if (!overlay || !card) return;
    overlay.classList.remove('hidden');
    card.classList.remove('pop-out');
    void card.offsetWidth;
    card.classList.add('pop-bounce');
}

function closeCopyNotice() {
    var overlay = document.getElementById('copy-overlay');
    var card = document.getElementById('copy-card');
    if (!overlay || !card) return;
    card.classList.remove('pop-bounce');
    void card.offsetWidth;
    card.classList.add('pop-out');
    setTimeout(function(){ overlay.classList.add('hidden'); }, 400);
}