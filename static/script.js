hljs.highlightAll();

// Global variables for chat conversation history
let conversationHistory = [];

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
    
    // Reset code state when page loads
    resetCodeState();

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

    // Expose appendMessage globally for use outside this closure
    window.appendMessage = appendMessage;


    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var text = (input && input.value || '').trim();
            if (!text) return;
            if (input) input.value = '';
            // Send free-form chat to backend using general chat type
            sendChatMessage(text, 'general', {});
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
                
                // Handle specific chat options
                if (opt === 'Help me learn a new block') {
                    handleBlockLearning();
                } else if (opt === "My code isn't working") {
                    handleDebugChat();
                } else if (opt === 'I want to add a new feature') {
                    handleImproveChat();
                } else if (opt === 'My code doesn\'t match my story') {
                    handleNarrativeAlignmentChat();
                }
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
    // Expose helpers for resetting chat startup options
    window.showChatStartupOptions = showChatStartupOptions;
    window.resetChatStartupOptions = function() {
        // Allow options to render again and insert them
        startupOptionsShown = false;
        showChatStartupOptions();
    };

    // Ensure chat resets as soon as a new upload is initiated
    var imageInput = document.getElementById('image-input');
    if (imageInput) {
        imageInput.addEventListener('click', function() {
            clearChatMessages();
        });
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

// Show encouragement popup immediately with empty content (delegates to openInlineEncouragement)
function showEncouragementPopup() {
    const encouragementText = document.getElementById('inline-encouragement-text');
    if (!encouragementText) return;
    encouragementText.innerHTML = '<h3>🎉 Getting feedback...</h3>';
    openInlineEncouragement();
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
        let dotsShownAt = 0;
        const dotsMinMs = 250;
        
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
                                // insert loading dots initially
                                const t = document.getElementById('inline-encouragement-text');
                                if (t && !t.dataset.loadingInit) {
                                    t.dataset.loadingInit = '1';
                                    t.innerHTML = '<h3>🎉 <span class="loading-dots"><span>.</span><span>.</span><span>.</span></span></h3>';
                                    console.log('Added loading dots to encouragement popup');
                                }
                                hasStarted = true;
                                dotsShownAt = Date.now();
                            }
                            
                            // Add word with proper spacing
                            currentText += data.word;
                            const t2 = document.getElementById('inline-encouragement-text');
                            if (t2 && t2.dataset.loadingInit === '1') {
                                const elapsed = Date.now() - dotsShownAt;
                                if (elapsed < dotsMinMs) {
                                    setTimeout(function(){
                                        t2.dataset.loadingInit = '0';
                                        t2.innerHTML = `<h3>🎉 ${currentText}</h3>`;
                                    }, dotsMinMs - elapsed);
                                } else {
                                    t2.dataset.loadingInit = '0';
                                    t2.innerHTML = `<h3>🎉 ${currentText}</h3>`;
                                }
                            } else {
                                document.getElementById('inline-encouragement-text').innerHTML = 
                                    `<h3>🎉 ${currentText}</h3>`;
                            }
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

// Show encouragement with improved animation
function showEncouragement(encouragementText) {
    const formatted = `<h3>🎉 ${encouragementText}</h3>`;
    document.getElementById('inline-encouragement-text').innerHTML = formatted;
    openInlineEncouragement();
}



// Suggestions removed



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

    // Clear chat when new image is captured
    clearChatMessages();

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


function clearChatMessages() {
    var messages = document.getElementById('chat-messages');
    if (messages) {
        // Keep only the initial AI message
        var initialMessage = messages.querySelector('.chat-msg.ai');
        messages.innerHTML = '';
        if (initialMessage) {
            messages.appendChild(initialMessage);
        }
        // Repopulate initial quick-start options
        if (typeof window.resetChatStartupOptions === 'function') {
            window.resetChatStartupOptions();
        }
    }
}

// Function to reset code state
function resetCodeState() {
    var contentElement = document.getElementById('content');
    if (contentElement) {
        contentElement.textContent = 'Your code will appear here (press Generate Code button).';
    }
    
    // Clear conversation history when resetting
    conversationHistory = [];
    
    // Also clear the backend code file
    fetch('/clear_code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    }).catch(error => {
        console.log('Error clearing backend code:', error);
    });
    
    console.log('Code state reset - now has no code');
}

function uploadImage() {
    var input = document.getElementById('image-input');
    var file = input.files[0];
    if (file) {
        // Clear chat when new image is uploaded
        clearChatMessages();
        
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

        // Reset the file input so selecting the same file again triggers change
        try { input.value = ''; } catch (e) { /* no-op */ }
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

// Suggestion modal controls removed

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

// Chat functionality for different help types
function hasExistingCode() {
    // Check if there's generated code content
    var contentElement = document.getElementById('content');
    if (!contentElement) return false;
    
    var codeText = contentElement.textContent || contentElement.innerText;
    
    // Check if it's actual generated code (not placeholder text)
    var isPlaceholder = codeText.trim() === 'Your code will appear here (press Generate Code button).' ||
                       codeText.trim() === '' ||
                       codeText.includes('// code will appear here after processing an image') ||
                       codeText.includes('Your code will appear here');

    var hasActualCode = codeText.length > 50 && 
                        (codeText.includes('input.') || 
                         codeText.includes('basic.') || 
                         codeText.includes('pins.') || 
                         codeText.includes('radio.') ||
                         codeText.includes('music.') ||
                         codeText.includes('led.') ||
                         codeText.includes('onButtonPressed') ||
                         codeText.includes('onGesture') ||
                         codeText.includes('forever') ||
                         codeText.includes('if (') ||
                         codeText.includes('showString') ||
                         codeText.includes('showIcon'));

    return !isPlaceholder && hasActualCode;
}

// Alternative async check that verifies with backend
function hasExistingCodeAsync() {
    return new Promise((resolve) => {
        fetch('/get_js_content')
            .then(response => response.text())
            .then(code => {
                var isPlaceholder = code.includes('// code will appear here after processing an image') ||
                                  code.includes('Your code will appear here') ||
                                  code.trim() === '' ||
                                  code.length < 50;
                
                var hasActualCode = code.length > 50 && 
                                  (code.includes('input.') || 
                                   code.includes('basic.') || 
                                   code.includes('pins.') || 
                                   code.includes('radio.') ||
                                   code.includes('music.') ||
                                   code.includes('led.') ||
                                   code.includes('onButtonPressed') ||
                                   code.includes('onGesture') ||
                                   code.includes('forever') ||
                                   code.includes('if (') ||
                                   code.includes('showString') ||
                                   code.includes('showIcon'));
                
                resolve(!isPlaceholder && hasActualCode);
            })
            .catch((error) => {
                console.log('Error checking code:', error);
                // If fetch fails, fall back to frontend check
                resolve(hasExistingCode());
            });
    });
}

function showNoCodeMessage(chatType) {
    var messages = document.getElementById('chat-messages');
    if (!messages) return;
    
    var noCodeMessages = {
        debug: 'Hmm... I don\'t see any of your code yet! 😊 Upload a picture of your code first, then I\'ll be able to help you figure out what\'s going wrong!',
        improve: 'Whoa there! 🛑 I\'d love to help you add cool features, but I need to see your code first! Take a picture of your project and then we can make it even more awesome!',
        narrative: 'Hey there! 🎨 I\'m excited to help you make your code match your story, but I need to see what you\'ve built so far! Upload a picture of your code and let\'s create something amazing together!'
    };
    
    var message = noCodeMessages[chatType] || 'Hmm... I don\'t see any of your code yet! Upload a picture of your code and I\'ll be there to help! 💪';
    
    // Create AI response message
    var aiMessage = document.createElement('div');
    aiMessage.className = 'chat-msg ai';
    
    var avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.classList.add('streaming-response');
    // Insert animated loading dots while waiting for stream
    bubble.innerHTML = '<span class="loading-dots"><span>.</span><span>.</span><span>.</span></span>';
    console.log('Added loading dots to chat bubble');
    
    aiMessage.appendChild(avatar);
    aiMessage.appendChild(bubble);
    messages.appendChild(aiMessage);
    
    // Stream the message
    streamContent(bubble, message);
    
    messages.scrollTop = messages.scrollHeight;
}

function handleDebugChat() {
    hasExistingCodeAsync().then(hasCode => {
        if (!hasCode) {
            showNoCodeMessage('debug');
            return;
        }
        startChatConversation('debug', 'Oh no! I see you\'re having trouble with your code! 😅\n\nDon\'t worry - debugging is totally normal when you\'re learning to code.\n\nCan you tell me what\'s happening? Is it not doing what you expected, or is there an error?');
    });
}

function handleImproveChat() {
    hasExistingCodeAsync().then(hasCode => {
        if (!hasCode) {
            showNoCodeMessage('improve');
            return;
        }
        startChatConversation('improve', 'Awesome! I love that you want to make your project even cooler! 🚀\n\nWhat kind of amazing new feature are you thinking about?\n\nMaybe add some sensors, make it talk to other micro:bits, or create some fun sounds and lights?');
    });
}

function handleNarrativeAlignmentChat() {
    hasExistingCodeAsync().then(hasCode => {
        if (!hasCode) {
            showNoCodeMessage('narrative');
            return;
        }
        startChatConversation('narrative', 'I totally get it! Sometimes our code doesn\'t quite match the awesome story we have in our heads! 🎭\n\nLet me help you figure out how to make your code tell the story you want.\n\nWhat kind of story or cool behavior are you trying to create?');
    });
}

function startChatConversation(chatType, initialMessage, context = {}) {
    var messages = document.getElementById('chat-messages');
    if (!messages) return;
    
    // Create AI response message
    var aiMessage = document.createElement('div');
    aiMessage.className = 'chat-msg ai';
    
    var avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.classList.add('streaming-response');
    
    aiMessage.appendChild(avatar);
    aiMessage.appendChild(bubble);
    messages.appendChild(aiMessage);
    
    // Stream the initial message
    streamContent(bubble, initialMessage);
    
    // Enable chat input for this conversation
    var chatInput = document.getElementById('chat-text');
    var chatForm = document.getElementById('chat-input-form');
    if (chatInput && chatForm) {
        chatInput.placeholder = 'Describe your question or problem...';
        chatInput.disabled = false;
        chatForm.onsubmit = function(e) {
            e.preventDefault();
            var userMessage = chatInput.value.trim();
            if (userMessage) {
                sendChatMessage(userMessage, chatType, context);
                chatInput.value = '';
            }
        };
    }
    
    messages.scrollTop = messages.scrollHeight;
}

function sendChatMessage(message, chatType, context = {}) {
    var messages = document.getElementById('chat-messages');
    if (!messages) return;
    
    // Add user message
    if (typeof window.appendMessage === 'function') {
        window.appendMessage('user', message);
    }
    
    // Create AI response message
    var aiMessage = document.createElement('div');
    aiMessage.className = 'chat-msg ai';
    
    var avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.classList.add('streaming-response');
    // Insert animated loading dots while waiting for stream
    bubble.innerHTML = '<span class="loading-dots"><span>.</span><span>.</span><span>.</span></span>';
    
    aiMessage.appendChild(avatar);
    aiMessage.appendChild(bubble);
    messages.appendChild(aiMessage);
    
    // Scroll to show the loading dots
    messages.scrollTop = messages.scrollHeight;
    
    // Disable input while processing
    var chatInput = document.getElementById('chat-text');
    if (chatInput) {
        chatInput.disabled = true;
        chatInput.placeholder = 'Thinking...';
    }
    
    // Add user message to conversation history
    conversationHistory.push({
        role: "user",
        content: message
    });
    
    // Send request to backend
    fetch('/chat_stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            type: chatType,
            message: message,
            context: context,
            conversation_history: conversationHistory
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.body.getReader();
    })
    .then(reader => {
        var decoder = new TextDecoder();
        var buffer = '';
        var bubble = aiMessage.querySelector('.bubble');
        var started = false;
        var bufferedContent = '';
        var dotsShownAt = Date.now();
        var dotsMinMs = 500; // Increased to 500ms to ensure dots are always visible
        var dotsRemoved = false;
        
        function readStream() {
            return reader.read().then(function(result) {
                if (result.done) {
                    // Add AI response to conversation history
                    var aiResponse = bubble.textContent || bubble.innerText;
                    if (aiResponse) {
                        conversationHistory.push({
                            role: "assistant",
                            content: aiResponse
                        });
                    }
                    
                    // Re-enable input when done
                    var chatInput = document.getElementById('chat-text');
                    if (chatInput) {
                        chatInput.disabled = false;
                        chatInput.placeholder = 'Ask another question...';
                        chatInput.focus();
                    }
                    return;
                }
                
                buffer += decoder.decode(result.value, { stream: true });
                var lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                lines.forEach(function(line) {
                    if (line.startsWith('data: ')) {
                        try {
                            var data = JSON.parse(line.slice(6));
                            if (data.word && bubble) {
                                // On first token, start buffering and set up dots removal
                                if (!started) {
                                    started = true;
                                    setTimeout(() => {
                                        bubble.innerHTML = bufferedContent; // Show all buffered content
                                        formatCodeBlocks(bubble);
                                        messages.scrollTop = messages.scrollHeight;
                                        dotsRemoved = true;
                                    }, dotsMinMs);
                                }
                                
                                // Buffer content until dots are removed
                                if (!dotsRemoved) {
                                    bufferedContent += (data.word === '<br>' ? '\n' : data.word);
                                } else {
                                    // After dots are removed, stream normally
                                    if (data.word === '<br>') {
                                        bubble.innerHTML += '<br>';
                                    } else {
                                        bubble.innerHTML += data.word;
                                    }
                                    formatCodeBlocks(bubble);
                                    messages.scrollTop = messages.scrollHeight;
                                }
                            }
                        } catch (e) {
                            // Ignore malformed JSON
                        }
                    }
                });
                
                return readStream();
            });
        }
        
        return readStream();
    })
    .catch(error => {
        console.error('Chat error:', error);
        
        // Create error message bubble
        var aiMessage = document.createElement('div');
        aiMessage.className = 'chat-msg ai';
        
        var avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
        
        var bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.textContent = 'Sorry, I\'m having trouble connecting right now. Please try again in a moment!';
        
        aiMessage.appendChild(avatar);
        aiMessage.appendChild(bubble);
        messages.appendChild(aiMessage);
        
        // Re-enable input
        var chatInput = document.getElementById('chat-text');
        if (chatInput) {
            chatInput.disabled = false;
            chatInput.placeholder = 'Try again...';
        }
    });
}

// Format code blocks in chat responses
function formatCodeBlocks(element) {
    if (!element) return;
    
    var content = element.innerHTML;
    
    // Find and format code blocks (```javascript ... ```)
    content = content.replace(/```javascript\s*([\s\S]*?)```/g, function(match, code) {
        return '<pre><code class="javascript">' + code.trim() + '</code></pre>';
    });
    
    // Find and format inline code (`code`)
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    element.innerHTML = content;
}

// streamContent is defined in block_learning.js; use that single implementation