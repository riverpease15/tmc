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

// Chat Drawer
document.addEventListener('DOMContentLoaded', function() {
    var drawer = document.getElementById('chat-drawer');
    var tab = document.getElementById('chat-drawer-tab');
    var form = document.getElementById('chat-input-form');
    var input = document.getElementById('chat-text');
    var messages = document.getElementById('chat-messages');
    var startupOptionsShown = false;

    function openDrawer() {
        if (!drawer) return;
        drawer.classList.remove('collapsed');
        drawer.setAttribute('aria-hidden', 'false');
        // Show quick-start options on first open
        if (!startupOptionsShown) {
            showChatStartupOptions();
            startupOptionsShown = true;
        }
    }

    function collapseDrawer() {
        if (!drawer) return;
        drawer.classList.add('collapsed');
        drawer.setAttribute('aria-hidden', 'true');
    }

    window.closeChatDrawer = collapseDrawer;

    if (tab) {
        tab.addEventListener('click', function() {
            if (drawer.classList.contains('collapsed')) {
                openDrawer();
                setTimeout(function(){ input && input.focus(); }, 250);
            } else {
                collapseDrawer();
            }
        });
    }

    function appendMessage(role, text) {
        if (!messages) return;
        var wrap = document.createElement('div');
        wrap.className = 'chat-msg ' + (role === 'user' ? 'user' : 'ai');
        var avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerHTML = role === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';
        var bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.textContent = text;
        if (role === 'user') {
            // user messages align right: place bubble before avatar visually by order
            wrap.appendChild(bubble);
            wrap.appendChild(avatar);
        } else {
            wrap.appendChild(avatar);
            wrap.appendChild(bubble);
        }
        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
    }

    // Lightweight canned reply for mock chat drawer
    function mockAiReply() {
        var hints = [
            "Cool! Tell me which buttons, pins, or sounds you want to use.",
            "Awesome idea. Do you want to add lights, sounds, or radio messages?",
            "Nice! Should it react to light, temperature, or a button press?",
            "Great! We can start simple. What should happen first?",
            "Got it. Do you want it to send a message to another micro:bit?"
        ];
        var msg = hints[Math.floor(Math.random() * hints.length)];
        setTimeout(function(){ appendMessage('ai', msg); }, 600);
    }

    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var text = (input && input.value || '').trim();
            if (!text) return;
            appendMessage('user', text);
            if (input) input.value = '';
            mockAiReply();
        });
    }

    // Render quick-start user-style options inside the chat
    function showChatStartupOptions() {
        if (!messages) return;
        if (document.getElementById('chat-options')) return;

        // Single chat message with one avatar and multiple option bubbles
        var wrap = document.createElement('div');
        wrap.className = 'chat-msg user';
        wrap.id = 'chat-options';

        var optionsContainer = document.createElement('div');
        optionsContainer.className = 'options-bubbles';

        var avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerHTML = '<i class="fa-solid fa-user"></i>';

        var options = [
            "My code isn't working",
            'I want to add a new feature',
            'Help me learn a new block',
            'My code doesn\'t match my story'
        ];

        options.forEach(function(opt) {
            var bubble = document.createElement('div');
            bubble.className = 'bubble chat-option';
            bubble.textContent = opt;
            bubble.setAttribute('role', 'button');
            bubble.setAttribute('tabindex', '0');
            bubble.addEventListener('click', function() {
                // Remove the options message
                wrap.remove();
                // Append the chosen text as a regular user message
                appendMessage('user', opt);
                mockAiReply();
            });
            bubble.addEventListener('keydown', function(ev){
                if (ev.key === 'Enter' || ev.key === ' ') {
                    ev.preventDefault();
                    bubble.click();
                }
            });
            optionsContainer.appendChild(bubble);
        });

        // user alignment: bubble(s) then avatar
        wrap.appendChild(optionsContainer);
        wrap.appendChild(avatar);

        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
    }
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

                // Show feedback button with animation
                showFeedbackButton();

                // Generate AI responses sequentially - only suggestions, no automatic encouragement
                generateStreamingIdea();
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

// Show feedback button with animation
function showFeedbackButton() {
    const feedbackBtn = document.getElementById('get-feedback-button');
    if (!feedbackBtn) return;
    
    // Show the button and trigger animation
    feedbackBtn.classList.remove('hidden');
    setTimeout(function() {
        feedbackBtn.classList.add('visible');
    }, 600); // Delay to let code generation finish
}

// Show encouragement popup immediately with empty content
function showEncouragementPopup() {
    const encouragement = document.getElementById('inline-encouragement');
    const codeBox = document.getElementById('code-box');
    const encouragementText = document.getElementById('inline-encouragement-text');
    
    if (!encouragement || !codeBox || !encouragementText) return;
    
    // Set empty content initially
    encouragementText.innerHTML = '<h3>🎉 Getting feedback...</h3>';
    
    // Show the encouragement card immediately
    encouragement.classList.remove('hidden');
    encouragement.classList.add('visible');
    
    // Add class to code box to make it smaller and move left
    codeBox.classList.add('with-encouragement');
}

// Get Feedback function - only generates encouragement when button is clicked
function getFeedback() {
    // Check if there's generated code to provide feedback on
    const contentElement = document.getElementById('content');
    if (!contentElement || contentElement.textContent.includes('Your code will appear here')) {
        alert('Please generate some code first before requesting feedback!');
        return;
    }
    
    // Show encouragement popup immediately with empty content
    showEncouragementPopup();
    
    // Generate encouragement when button is clicked
    generateStreamingEncouragement();
}

// Removed legacy parallel generator; using dedicated streaming functions

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
        let streamedBlocks = [];
        
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
                        
                        // Server may stream blocks separately for the UI
                        if (Array.isArray(data.blocks)) {
                            streamedBlocks = data.blocks;
                            const blocksHtml = streamedBlocks.map(block => `<li><code>${block}</code></li>`).join('');
                            const base = document.getElementById('suggestion-text').innerHTML;
                            document.getElementById('suggestion-text').innerHTML =
                                `${base}
                                 <p><strong>🧩 Blocks to Explore:</strong></p>
                                 <ul>${blocksHtml}</ul>`;
                        }

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
                            // Finalize idea text with a light grammar tidy
                            currentText = tidyIdeaSentence(currentText);
                            document.getElementById('suggestion-text').innerHTML = 
                                `<p><strong>💡 Idea to Try:</strong> ${currentText}</p>`;

                            // If no streamed blocks, extract from final text as fallback
                            const blocks = streamedBlocks.length ? streamedBlocks : extractBlocksFromIdea(currentText);
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
            idea: "What if you added some sound effects when you press a button and sent a message to other devices?",
            blocks: ["ON BUTTON A", "PLAY SOUND", "SEND STRING", "SHOW ICON"]
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

// Light grammar cleanup for streamed idea text (post-processing)
function tidyIdeaSentence(text) {
    if (!text) return text;
    let t = text;
    // Normalize whitespace
    t = t.replace(/\s+/g, ' ').trim();
    // Remove leftover unmatched parentheses if any
    t = t.replace(/\([^)]*$/g, '').trim();
    // Common fixes
    t = t.replace(/\bwhen you press and read from pin\b/i, 'when you press and the value from pin');
    t = t.replace(/\bwhen you press and the read from pin\b/i, 'when you press and the value from pin');
    t = t.replace(/\bshowed a string\b/i, 'showed a string');
    // Ensure it starts with a capital and ends with a question mark
    t = t.charAt(0).toUpperCase() + t.slice(1);
    if (!/[?!.]$/.test(t)) t += '?';
    return t;
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