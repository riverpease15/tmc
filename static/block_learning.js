// Block Learning System
// Handles the "Help me learn a new block" chat option

class BlockLearningSystem {
    constructor() {
        this.blocksMap = null;
        this.currentStep = 'category'; // 'category', 'block', 'description'
        this.selectedCategory = null;
        this.selectedBlock = null;
    }

    async loadBlocksMap() {
        if (this.blocksMap) return this.blocksMap;
        
        try {
            const response = await fetch('/static/blocks_map.json');
            this.blocksMap = await response.json();
            return this.blocksMap;
        } catch (error) {
            console.error('Error loading blocks map:', error);
            return null;
        }
    }

    getCategories() {
        if (!this.blocksMap) return [];
        
        // Get categories that have blocks with descriptions
        const categoriesWithDescriptions = [];
        for (const [category, blocks] of Object.entries(this.blocksMap)) {
            if (typeof blocks === 'object' && blocks !== null) {
                // Check if this category has blocks with descriptions
                const hasDescriptions = Object.values(blocks).some(block => 
                    typeof block === 'object' && block.description
                );
                if (hasDescriptions) {
                    categoriesWithDescriptions.push({
                        name: category,
                        displayName: this.getCategoryDisplayName(category),
                        blockCount: Object.keys(blocks).length
                    });
                }
            }
        }
        
        return categoriesWithDescriptions;
    }

    getCategoryDisplayName(category) {
        const displayNames = {
            'basic': 'Basic',
            'input': 'Sensors',
            'music': 'Music',
            'events': 'Events',
            'logic': 'Logic',
            'loops': 'Loops',
            'math': 'Math',
            'led': 'LEDs',
            'control': 'Control',
            'variables': 'Variables',
            'pins': 'Pins',
            'radio': 'Radio'
        };
        return displayNames[category] || category.charAt(0).toUpperCase() + category.slice(1);
    }

    getBlocksForCategory(category) {
        if (!this.blocksMap || !this.blocksMap[category]) return [];
        
        const blocks = [];
        for (const [blockName, blockData] of Object.entries(this.blocksMap[category])) {
            if (typeof blockData === 'object' && blockData.description) {
                blocks.push({
                    name: blockName,
                    description: blockData.description,
                    template: blockData.template,
                    image: blockData.image
                });
            }
        }
        
        return blocks;
    }

    showCategorySelection() {
        const categories = this.getCategories();
        
        let message = "Great! Let's learn about micro:bit blocks! 🎯\n\n";
        message += "Which category of blocks would you like to explore?\n\n";
        
        // Create category buttons
        const categoryButtons = categories.map(category => ({
            text: category.displayName,
            value: category.name,
            action: () => this.selectCategory(category.name)
        }));
        
        return {
            message: message,
            buttons: categoryButtons,
            isCategoryStep: true
        };
    }

    showInitialOptions() {
        let message = "Awesome! Let's learn about micro:bit blocks! 🎯\n\n";
        message += "Do you want to learn about a specific block you have in mind, or would you like to explore all the different categories of blocks?\n\n";
        
        const buttons = [
            { 
                text: "Learn About a Specific Block", 
                value: "specific_block", 
                action: () => this.requestSpecificBlock() 
            },
            { 
                text: "See All Block Categories", 
                value: "all_categories", 
                action: () => this.showCategorySelection() 
            }
        ];
        
        return {
            message: message,
            buttons: buttons,
            isCategoryStep: false
        };
    }

    requestSpecificBlock() {
        this.currentStep = 'searching';
        return {
            message: "Perfect! What's the name of the block you'd like to learn about? Just type it in and I'll help you explore it! 🔍",
            buttons: [],
            isCategoryStep: false,
            requiresUserInput: true
        };
    }

    searchForBlock(blockName) {
        if (!this.blocksMap) return null;
        
        // Search through all categories for a matching block
        for (const [category, blocks] of Object.entries(this.blocksMap)) {
            if (typeof blocks === 'object' && blocks !== null) {
                for (const [blockKey, blockData] of Object.entries(blocks)) {
                    if (typeof blockData === 'object' && blockData.description) {
                        // Check if the block name matches (case insensitive)
                        if (blockKey.toLowerCase() === blockName.toLowerCase()) {
                            return {
                                block: {
                                    name: blockKey,
                                    description: blockData.description,
                                    template: blockData.template,
                                    image: blockData.image
                                },
                                category: category
                            };
                        }
                    }
                }
            }
        }
        return null;
    }

    showBlockSearchResult(blockName) {
        const result = this.searchForBlock(blockName);
        
        if (result) {
            this.selectedBlock = result.block.name;
            this.selectedCategory = result.category;
            this.currentStep = 'description';
            
            let message = `🎉 **${result.block.name}**\n\n`;
            message += `${result.block.description}\n\n`;
            message += `Would you like to learn more about this block or explore other blocks?`;
            
            const buttons = [
                { text: "Learn More (AI Help)", value: "learn_more", action: () => this.requestMoreHelp() },
                { text: "Try Another Block", value: "another_block", action: () => this.requestSpecificBlock() },
                { text: "See All Categories", value: "all_categories", action: () => this.showCategorySelection() }
            ];
            
            return {
                message: message,
                buttons: buttons
            };
        } else {
            let message = `Hmm, I couldn't find a block called "${blockName}". 🤔\n\n`;
            message += `Don't worry! You can try:\n`;
            message += `• Checking the spelling\n`;
            message += `• Looking at all the block categories instead\n`;
            message += `• Asking me about a different block name\n\n`;
            message += `What would you like to do?`;
            
            const buttons = [
                { text: "Try Another Block Name", value: "try_again", action: () => this.requestSpecificBlock() },
                { text: "See All Categories", value: "all_categories", action: () => this.showCategorySelection() }
            ];
            
            return {
                message: message,
                buttons: buttons
            };
        }
    }

    selectCategory(categoryName) {
        this.selectedCategory = categoryName;
        this.currentStep = 'block';
        return this.showBlockSelection();
    }

    showBlockSelection() {
        const blocks = this.getBlocksForCategory(this.selectedCategory);
        
        let message = `Awesome! Here are the ${this.getCategoryDisplayName(this.selectedCategory)} blocks you can learn about:\n\n`;
        
        // Create block buttons
        const blockButtons = blocks.map(block => ({
            text: block.name,
            value: block.name,
            action: () => this.selectBlock(block.name)
        }));
        
        return {
            message: message,
            buttons: blockButtons
        };
    }

    selectBlock(blockName) {
        this.selectedBlock = blockName;
        this.currentStep = 'description';
        return this.showBlockDescription();
    }

    showBlockDescription() {
        const blocks = this.getBlocksForCategory(this.selectedCategory);
        const block = blocks.find(b => b.name === this.selectedBlock);
        
        if (!block) {
            return {
                message: "Sorry, I couldn't find that block. Let's try again!",
                buttons: [{ text: "Start Over", action: () => this.reset() }]
            };
        }
        
        let message = `🎉 **${this.selectedBlock}**\n\n`;
        message += `${block.description}\n\n`;
        message += `Would you like to learn more about this block or explore other blocks?`;
        
        const buttons = [
            { text: "Learn More (AI Help)", value: "learn_more", action: () => this.requestMoreHelp() },
            { text: "Try Another Block", value: "another_block", action: () => this.showBlockSelection() },
            { text: "Different Category", value: "different_category", action: () => this.showCategorySelection() }
        ];
        
        return {
            message: message,
            buttons: buttons
        };
    }

    requestMoreHelp() {
        return {
            message: "Great choice! I'll connect you with our AI assistant to get more detailed help with this block. The AI can provide examples, troubleshooting tips, and advanced usage ideas! 🤖",
            buttons: [
                { text: "Continue to AI Chat", value: "ai_chat", action: () => this.transferToAI() },
                { text: "Back to Block Info", value: "back", action: () => this.showBlockDescription() }
            ]
        };
    }

    transferToAI() {
        // Start a chat conversation with block learning context
        const context = {
            block: this.selectedBlock,
            category: this.selectedCategory,
            description: this.getBlocksForCategory(this.selectedCategory).find(b => b.name === this.selectedBlock)?.description
        };
        
        // Use the chat system with learn_block type
        if (typeof startChatConversation === 'function') {
            startChatConversation('learn_block', `Awesome! Let's dive into the **${this.selectedBlock}** block! 🤓 This is a ${this.getCategoryDisplayName(this.selectedCategory)} block that ${context.description || 'helps you create super cool interactive projects'}. What would you like to know about it? Maybe how to use it, what it does, or how to combine it with other blocks?`, context);
        }
        
        return null; // Don't return a message since we're transferring to chat
    }

    reset() {
        this.currentStep = 'category';
        this.selectedCategory = null;
        this.selectedBlock = null;
        return this.showCategorySelection();
    }

    async handleUserInput(input) {
        await this.loadBlocksMap();
        
        switch (this.currentStep) {
            case 'category':
                return this.showCategorySelection();
            case 'block':
                return this.showBlockSelection();
            case 'description':
                return this.showBlockDescription();
            default:
                return this.showCategorySelection();
        }
    }
}

// Simple markdown parser for block descriptions
function parseMarkdown(text) {
    return text
        // Bold text: **text** -> <strong>text</strong>
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // Italic text: *text* -> <em>text</em>
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // Code blocks: ```language\ncode\n``` -> <pre><code>code</code></pre>
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        // Inline code: `code` -> <code>code</code>
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Headers: ## text -> <h2>text</h2>
        .replace(/^## (.*)$/gm, '<h2>$1</h2>')
        // Headers: # text -> <h1>text</h1>
        .replace(/^# (.*)$/gm, '<h1>$1</h1>')
        // Convert line breaks to <br>, but not trailing ones
        .replace(/\n(?!$)/g, '<br>');
}

// Global instance
window.blockLearningSystem = new BlockLearningSystem();

// Function to handle the "Help me learn a new block" option
window.handleBlockLearning = async function() {
    const system = window.blockLearningSystem;
    await system.loadBlocksMap();
    
    const result = system.showInitialOptions();
    
    // Display the message and buttons in the chat
    displayBlockLearningResponse(result, result.isCategoryStep);
};

function displayBlockLearningResponse(result, isCategoryStep = false) {
    const messages = document.getElementById('chat-messages');
    if (!messages) return;
    
    // Create AI response message for the text
    const aiMessage = document.createElement('div');
    aiMessage.className = 'chat-msg ai';
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    
    // Use bubble class like the initial message
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    
    // Add streaming animation to the bubble
    bubble.classList.add('streaming-response');
    
    aiMessage.appendChild(avatar);
    aiMessage.appendChild(bubble);
    messages.appendChild(aiMessage);
    
    // Stream the content with typing animation
    streamContent(bubble, result.message);
    
    // Add buttons if they exist (as user-style options) - delay to show after streaming
    if (result.buttons && result.buttons.length > 0) {
        // Calculate delay based on text length to ensure streaming completes
        const textLength = result.message.length;
        const streamingDelay = Math.max(2000, textLength * 25); // At least 2 seconds, or 25ms per character
        
        setTimeout(() => {
            const userMessage = document.createElement('div');
            userMessage.className = 'chat-msg user';
            
            // Add class for category options to make them wider
            if (isCategoryStep) {
                userMessage.classList.add('block-learning-category-options');
            }
            
            const userAvatar = document.createElement('div');
            userAvatar.className = 'avatar';
            userAvatar.innerHTML = '<i class="fa-solid fa-user"></i>';
            
            const buttonsContainer = document.createElement('div');
            buttonsContainer.className = 'options-bubbles';
            
            result.buttons.forEach((button, index) => {
                const buttonEl = document.createElement('div');
                buttonEl.className = 'bubble chat-option';
                buttonEl.textContent = button.text;
                buttonEl.setAttribute('role', 'button');
                buttonEl.setAttribute('tabindex', '0');
                buttonEl.style.opacity = '0';
                buttonEl.style.transform = 'translateY(20px)';
                buttonEl.style.transition = 'all 0.3s ease';
                
                buttonEl.addEventListener('click', () => {
                    // Apply smooth transitions to selected button and user avatar BEFORE any changes
                    buttonEl.style.transition = 'all 0.3s ease';
                    const userAvatar = userMessage.querySelector('.avatar');
                    if (userAvatar) {
                        userAvatar.style.transition = 'all 0.3s ease';
                    }
                    
                    // Animate selected button to show selection
                    buttonEl.style.transform = 'scale(1.05)';
                    
                    // Animate and remove unselected buttons
                    result.buttons.forEach((otherButton, otherIndex) => {
                        if (otherIndex !== index) {
                            const otherButtonEl = buttonsContainer.children[otherIndex];
                            otherButtonEl.style.transform = 'translateY(-10px)';
                            otherButtonEl.style.opacity = '0';
                            otherButtonEl.style.transition = 'all 0.2s ease';
                            
                            // Remove from DOM after animation
                            setTimeout(() => {
                                if (otherButtonEl.parentNode) {
                                    otherButtonEl.parentNode.removeChild(otherButtonEl);
                                }
                            }, 200);
                        }
                    });
                    
                    // Execute action after animation
                    setTimeout(() => {
                        if (button.action) {
                            const nextResult = button.action();
                            if (nextResult) {
                                displayBlockLearningResponse(nextResult, nextResult.isCategoryStep);
                            }
                        }
                    }, 300);
                });
                
                buttonEl.addEventListener('keydown', function(ev){
                    if (ev.key === 'Enter' || ev.key === ' ') {
                        ev.preventDefault();
                        buttonEl.click();
                    }
                });
                
                buttonsContainer.appendChild(buttonEl);
                
                // Animate button in with staggered delay
                setTimeout(() => {
                    buttonEl.style.opacity = '1';
                    buttonEl.style.transform = 'translateY(0)';
                }, index * 100 + 100); // 100ms delay between each button
            });
            
            // user alignment: bubble(s) then avatar (same as original)
            userMessage.appendChild(buttonsContainer);
            userMessage.appendChild(userAvatar);
            messages.appendChild(userMessage);
            messages.scrollTop = messages.scrollHeight;
        }, streamingDelay); // Dynamic delay based on text length
    }
}

// Stream content with typing animation
function streamContent(element, text) {
    let currentIndex = 0;
    
    // Add loading dots initially
    element.innerHTML = '<div class="loading-dots"><span>.</span><span>.</span><span>.</span></div>';
    
    function streamNext() {
        if (currentIndex < text.length) {
            // Remove loading dots when we start streaming
            if (element.querySelector('.loading-dots')) {
                element.innerHTML = '';
            }
            
            // Add the current character
            element.innerHTML += text[currentIndex];
            currentIndex++;
            
            // Apply markdown formatting to the current content
            const currentContent = element.innerHTML;
            element.innerHTML = parseMarkdown(currentContent);
            
            // Scroll to bottom as content appears
            const messages = document.getElementById('chat-messages');
            if (messages) {
                messages.scrollTop = messages.scrollHeight;
            }
            
            // Continue streaming with faster timing
            setTimeout(streamNext, Math.random() * 20 + 10);
        } else {
            // Remove streaming class when complete
            element.classList.remove('streaming-response');
        }
    }
    
    // Start streaming after a brief delay
    setTimeout(streamNext, 600);
}
