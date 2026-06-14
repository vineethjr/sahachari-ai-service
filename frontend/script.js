const CONFIG = {
  API_URL: 'http://localhost:8000',
 

  CHAT_ENDPOINT: '/chat',

  HEALTH_ENDPOINT: '/health',

  MAX_HISTORY_ITEMS: 20,
 

  TYPING_MIN_MS: 800,
 
};

const state = {


  currentChatId: null,
 
  isLoading: false,

  isDarkMode: true,
  
};


const el = {
  messagesContainer: document.getElementById('messagesContainer'),
  userInput:         document.getElementById('userInput'),
  sendBtn:           document.getElementById('sendBtn'),
  sendIcon:          document.getElementById('sendIcon'),
  charCount:         document.getElementById('charCount'),
  chatHistoryList:   document.getElementById('chatHistoryList'),
  currentChatTitle:  document.getElementById('currentChatTitle'),
  welcomeScreen:     document.getElementById('welcomeScreen'),
  themeIcon:         document.getElementById('themeIcon'),
  themeLabel:        document.getElementById('themeLabel'),
  sidebar:           document.getElementById('sidebar'),
  sidebarOverlay:    document.getElementById('sidebarOverlay'),
  statusDot:         document.getElementById('statusDot'),
  statusText:        document.getElementById('statusText'),
  sourceModalBody:   document.getElementById('sourceModalBody'),
  toastBody:         document.getElementById('toastBody'),
};


document.addEventListener('DOMContentLoaded', () => {
  

  loadThemePreference();
  loadChatsFromStorage();
  startNewChat();           // Always open fresh on page load
  setupInputListener();
  checkAPIHealth();

  // Recheck API health every 30 seconds
  setInterval(checkAPIHealth, 30000);
});



async function sendMessage() {
 

  // 1. Get and validate input
  const question = el.userInput.value.trim();
 

  if (!question) return;             // Do nothing if input is empty
  if (state.isLoading) return;       // Do nothing if already waiting for response

  // 2. Clear input and reset UI
  el.userInput.value = '';
  autoResize(el.userInput);          // Reset textarea to single line
  updateCharCount(el.userInput);     // Reset character count
  disableSendButton();

  // 3. Add user message to the chat display
  addMessageToDOM({
    role: 'user',
    content: question,
    timestamp: new Date(),
  });

  // 4. Hide the welcome screen (first message sent)
  hideWelcomeScreen();

  // 5. Update the chat title if this is the first message
  ensureChatTitle(question);

  // 6. Save user message to current chat state
  addMessageToCurrentChat({ role: 'user', content: question, timestamp: new Date() });

  // 7. Show typing animation while we wait
  const typingId = showTypingIndicator();

  // 8. Mark loading state
  state.isLoading = true;

  try {
    // 9. Call FastAPI
    const response = await callAPI(question);

    // 10. Remove typing indicator
    hideTypingIndicator(typingId);

    // 11. Add bot message to DOM
    addMessageToDOM({
      role: 'bot',
      content: response.answer,
      timestamp: new Date(),
      sources: response.sources || [],
    });

    // 12. Save bot message to state
    addMessageToCurrentChat({
      role: 'bot',
      content: response.answer,
      timestamp: new Date(),
      sources: response.sources || [],
    });

    // 13. Save updated chat to localStorage
    saveChatsToStorage();

  } catch (error) {
   
    hideTypingIndicator(typingId);

    // Show error message as bot response
    addMessageToDOM({
      role: 'bot',
      content: formatErrorMessage(error),
      timestamp: new Date(),
      isError: true,
    });

    showToast(getErrorToastMessage(error), 'error');

  } finally {
    
    state.isLoading = false;
    enableSendButton();
    scrollToBottom();
  }
}



async function callAPI(question) {
  const requestBody = {
    question: question,
    
  };

  const response = await fetch(`${CONFIG.API_URL}${CONFIG.CHAT_ENDPOINT}`, {
    method: 'POST',

    headers: {
      'Content-Type': 'application/json',
    },

    body: JSON.stringify(requestBody),
  });


  if (!response.ok) {
    /*
      response.ok is true if status is 200-299.
      If FastAPI returns 404, 500, 422 (validation error), etc., we throw.
    */
    const errorData = await response.json().catch(() => ({}));
    throw new APIError(
      errorData.detail || `API Error: ${response.status} ${response.statusText}`,
      response.status
    );
  }

  const data = await response.json();
  /*
    .json() reads the response body and parses it from JSON string to JS object.
    { "answer": "...", "sources": [...] } → JS object we can use
  */

  // Validate response structure
  if (!data.answer) {
    throw new APIError('Invalid response format from API: missing "answer" field');
  }

  return data;
  /*
    Returns: { answer: "...", sources: [...] }
    This goes back to sendMessage() which awaits this call.
  */
}


/* ================================================================
   6. DOM RENDERING
   ================================================================
  These functions create and insert HTML elements into the page.
  This is how we make the chat appear visually.
*/

/**
 * addMessageToDOM() — Creates and inserts a message bubble into the chat.
 * @param {Object} msg - { role, content, timestamp, sources?, isError? }
 */
function addMessageToDOM(msg) {
  const isUser = msg.role === 'user';
  const isError = msg.isError || false;

  // Create the outer message container
  const messageDiv = document.createElement('div');
  /*
    document.createElement('div') creates a new <div> element in memory.
    It's not in the page yet — we add it at the end with appendChild().
  */

  messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
  messageDiv.dataset.messageId = generateId();
  /*
    dataset.messageId sets: <div data-message-id="xyz">
    We can retrieve this later with element.dataset.messageId
  */

  // Format the timestamp
  const timeStr = formatTime(msg.timestamp);

  // Build the sources button HTML (only for bot messages with sources)
  const sourcesButtonHTML = (!isUser && msg.sources && msg.sources.length > 0)
    ? `<button class="source-badge" onclick="openSourceModal(this)"
              data-sources='${escapeJSON(msg.sources)}'>
         <i class="bi bi-file-earmark-text"></i>
         ${msg.sources.length} source${msg.sources.length > 1 ? 's' : ''}
       </button>`
    : '';

  // Format content — detect and style code blocks, URLs, etc.
  const formattedContent = formatMessageContent(msg.content);

  // Build the full message HTML using a template literal
  /*
    Template literals (backticks) let us write multi-line strings with ${} interpolation.
    Much cleaner than string concatenation with +.
  */
  messageDiv.innerHTML = `
    <div class="message-row">
      <div class="message-avatar ${isUser ? 'user-avatar' : 'bot-avatar'}">
        ${isUser
          ? '<i class="bi bi-person-fill"></i>'
          : '<i class="bi bi-stars"></i>'
        }
      </div>
      <div class="message-bubble ${isUser ? 'user-bubble' : 'bot-bubble'} ${isError ? 'error-bubble' : ''}">
        <div class="message-text">${formattedContent}</div>
      </div>
    </div>
    <div class="message-meta">
      <span class="message-timestamp">${timeStr}</span>
      ${sourcesButtonHTML}
      <div class="message-actions">
        ${!isUser ? `
          <button class="action-btn" onclick="copyMessage(this)" title="Copy answer">
            <i class="bi bi-copy"></i> Copy
          </button>
        ` : ''}
      </div>
    </div>
  `;

  // Insert into the messages container
  el.messagesContainer.appendChild(messageDiv);
  /*
    appendChild() adds the element as the LAST child.
    So messages appear in order, newest at bottom.
  */

  // Scroll to the new message
  scrollToBottom();
}


/**
 * showTypingIndicator() — Shows the "bot is thinking" animation.
 * Returns an ID so we can remove the specific indicator later.
 * @returns {string} id - The unique ID of this typing indicator
 */
function showTypingIndicator() {
  const id = `typing-${Date.now()}`;
  /*
    Date.now() returns milliseconds since Jan 1, 1970 (Unix timestamp).
    Using it as ID guarantees uniqueness since it always increases.
  */

  const typingDiv = document.createElement('div');
  typingDiv.className = 'typing-indicator';
  typingDiv.id = id;

  typingDiv.innerHTML = `
    <div class="message-avatar bot-avatar">
      <i class="bi bi-stars"></i>
    </div>
    <div class="typing-bubble">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <span class="typing-label">Searching documents...</span>
    </div>
  `;

  el.messagesContainer.appendChild(typingDiv);
  scrollToBottom();

  return id;
}

/**
 * hideTypingIndicator(id) — Removes the typing animation from the DOM.
 * @param {string} id - The ID returned by showTypingIndicator()
 */
function hideTypingIndicator(id) {
  const typingEl = document.getElementById(id);
  if (typingEl) {
    typingEl.remove();
    /*
      .remove() detaches the element from the DOM entirely.
      The browser garbage-collects the memory.
    */
  }
}

function startNewChat() {
  // Deactivate previous chat in sidebar
  document.querySelectorAll('.history-item').forEach(item => {
    item.classList.remove('active');
  });

  // Create new chat object
  const newChat = {
    id: generateId(),
    title: 'New Chat',
    messages: [],
    createdAt: new Date().toISOString(),
  };

  // Add to state
  state.chats.unshift(newChat);
  /*
    .unshift() adds to the BEGINNING of the array (newest first).
    Like .push() but at front instead of back.
  */

  state.currentChatId = newChat.id;

  // Clear messages area
  el.messagesContainer.innerHTML = '';

  // Show welcome screen
  showWelcomeScreen();

  // Update header title
  el.currentChatTitle.textContent = 'New Conversation';

  // Re-render sidebar history list
  renderChatHistory();

  // Trim history if too many chats
  if (state.chats.length > CONFIG.MAX_HISTORY_ITEMS) {
    state.chats = state.chats.slice(0, CONFIG.MAX_HISTORY_ITEMS);
  }

  // Focus the input
  el.userInput.focus();
}

/**
 * loadChat(chatId) — Loads a previous chat from history into the main area.
 * @param {string} chatId
 */
function loadChat(chatId) {
  const chat = state.chats.find(c => c.id === chatId);
  if (!chat) return;

  state.currentChatId = chatId;

  // Clear current messages
  el.messagesContainer.innerHTML = '';

  // Update header
  el.currentChatTitle.textContent = chat.title;

  if (chat.messages.length === 0) {
    showWelcomeScreen();
    return;
  }

  hideWelcomeScreen();

  // Re-render all messages
  chat.messages.forEach(msg => addMessageToDOM(msg));

  // Update sidebar active state
  renderChatHistory();

  scrollToBottom(false);   // Jump to bottom without animation
}

/**
 * renderChatHistory() — Rebuilds the sidebar chat list from state.chats.
 */
function renderChatHistory() {
  // Filter out empty chats (no messages yet)
  const chatsWithMessages = state.chats.filter(c => c.messages.length > 0);

  if (chatsWithMessages.length === 0) {
    el.chatHistoryList.innerHTML = `
      <li class="history-empty">
        <i class="bi bi-chat-dots"></i>
        <span>No chats yet</span>
      </li>
    `;
    return;
  }

  // Build list items
  el.chatHistoryList.innerHTML = chatsWithMessages.map(chat => `
    <li class="history-item ${chat.id === state.currentChatId ? 'active' : ''}"
        onclick="loadChat('${chat.id}')"
        title="${escapeHTML(chat.title)}">
      <i class="bi bi-chat-text"></i>
      <span class="history-item-text">${escapeHTML(chat.title)}</span>
    </li>
  `).join('');
  /*
    .map() transforms each chat object into an HTML string.
    .join('') concatenates them into one string with no separator.
  */
}

/**
 * addMessageToCurrentChat(msg) — Adds a message to the current chat's messages array.
 */
function addMessageToCurrentChat(msg) {
  const currentChat = state.chats.find(c => c.id === state.currentChatId);
  if (currentChat) {
    currentChat.messages.push(msg);
  }
}

/**
 * ensureChatTitle(question) — Sets the chat title from the first user message.
 */
function ensureChatTitle(question) {
  const currentChat = state.chats.find(c => c.id === state.currentChatId);
  if (!currentChat || currentChat.title !== 'New Chat') return;
  /*
    Only set title from first message (when it's still "New Chat").
    Subsequent messages don't change the title.
  */

  // Use first 40 characters of question as title
  const title = question.length > 40
    ? question.substring(0, 40) + '...'
    : question;

  currentChat.title = title;
  el.currentChatTitle.textContent = title;
  renderChatHistory();
}

/**
 * clearCurrentChat() — Clears all messages in the current chat.
 */
function clearCurrentChat() {
  const currentChat = state.chats.find(c => c.id === state.currentChatId);
  if (!currentChat) return;

  if (currentChat.messages.length === 0) {
    showToast('Chat is already empty', 'info');
    return;
  }

  currentChat.messages = [];
  currentChat.title = 'New Chat';
  el.messagesContainer.innerHTML = '';
  showWelcomeScreen();
  el.currentChatTitle.textContent = 'New Conversation';
  renderChatHistory();
  saveChatsToStorage();
  showToast('Chat cleared', 'info');
}

/* ─── localStorage Persistence ─── */

/**
 * saveChatsToStorage() — Serializes state.chats to localStorage.
 * localStorage stores key-value pairs that persist after page close.
 */
function saveChatsToStorage() {
  try {
    localStorage.setItem('sahachari_chats', JSON.stringify(state.chats));
    /*
      JSON.stringify converts JS objects/arrays to a JSON string.
      localStorage can only store strings, so we must stringify first.
    */
  } catch (e) {
    // localStorage can be full (5-10MB limit) or blocked in private mode
    console.warn('Could not save chats to localStorage:', e);
  }
}

/**
 * loadChatsFromStorage() — Restores chats from localStorage on page load.
 */
function loadChatsFromStorage() {
  try {
    const saved = localStorage.getItem('sahachari_chats');
    if (saved) {
      state.chats = JSON.parse(saved);
      /*
        JSON.parse converts the stored string back to a JS array of objects.
      */
      renderChatHistory();
    }
  } catch (e) {
    console.warn('Could not load chats from localStorage:', e);
    state.chats = [];
  }
}


/* ================================================================
   8. THEME TOGGLING
   ================================================================ */

/**
 * toggleTheme() — Switches between dark and light mode.
 */
function toggleTheme() {
  state.isDarkMode = !state.isDarkMode;
  /*
    !state.isDarkMode flips true to false and false to true.
  */

  const theme = state.isDarkMode ? 'dark' : 'light';

  // Set data-theme attribute on <html> element
  document.documentElement.setAttribute('data-theme', theme);
  /*
    document.documentElement is the <html> element.
    Our CSS [data-theme="dark"] rules activate/deactivate based on this attribute.
  */

  // Update the toggle button icon and label
  el.themeIcon.className = state.isDarkMode
    ? 'bi bi-moon-stars-fill'
    : 'bi bi-sun-fill';

  el.themeLabel.textContent = state.isDarkMode ? 'Dark Mode' : 'Light Mode';

  // Save preference to localStorage
  localStorage.setItem('sahachari_theme', theme);
}

/**
 * loadThemePreference() — Restores saved theme on page load.
 */
function loadThemePreference() {
  const saved = localStorage.getItem('sahachari_theme');
  if (saved) {
    state.isDarkMode = saved === 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    el.themeIcon.className = state.isDarkMode
      ? 'bi bi-moon-stars-fill'
      : 'bi bi-sun-fill';
    el.themeLabel.textContent = state.isDarkMode ? 'Dark Mode' : 'Light Mode';
  }
}


/* ================================================================
   9. SIDEBAR MANAGEMENT (Mobile)
   ================================================================ */

function openSidebar() {
  el.sidebar.classList.add('open');
  el.sidebarOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
  /*
    Prevent the main page from scrolling while sidebar is open on mobile.
  */
}

function closeSidebar() {
  el.sidebar.classList.remove('open');
  el.sidebarOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

// Close sidebar when a chat history item is clicked on mobile
const originalLoadChat = loadChat;
// We wrap loadChat to also close sidebar on mobile
window.loadChatAndClose = function(chatId) {
  loadChatAndClose(chatId);
};


/* ================================================================
   10. UTILITY FUNCTIONS
   ================================================================ */

/**
 * scrollToBottom(smooth=true) — Scrolls messages area to the latest message.
 */
function scrollToBottom(smooth = true) {
  el.messagesContainer.scrollTo({
    top: el.messagesContainer.scrollHeight,
    /*
      scrollHeight is the total scrollable height (including overflow).
      Setting scrollTop to scrollHeight scrolls to absolute bottom.
    */
    behavior: smooth ? 'smooth' : 'instant',
  });
}

/**
 * showWelcomeScreen() / hideWelcomeScreen() — Controls welcome screen visibility.
 */
function showWelcomeScreen() {
  // Check if welcome screen already exists
  if (!document.getElementById('welcomeScreen')) {
    const welcome = document.createElement('div');
    welcome.id = 'welcomeScreen';
    welcome.className = 'welcome-screen';
    welcome.innerHTML = `
      <div class="welcome-content">
        <h2 class="welcome-title">How can I help you today?</h2>
        <p class="welcome-subtitle">Ask a question to search across available documentation.</p>
        <div class="suggested-prompts">
          <div class="suggested-label">Try asking:</div>
          <div class="prompt-chips">
            <button class="prompt-chip" onclick="usePrompt(this)">What documents are available?</button>
            <button class="prompt-chip" onclick="usePrompt(this)">Summarize the key topics</button>
            <button class="prompt-chip" onclick="usePrompt(this)">What are the main guidelines?</button>
            <button class="prompt-chip" onclick="usePrompt(this)">How does the process work?</button>
          </div>
        </div>
      </div>
    `;
    el.messagesContainer.insertBefore(welcome, el.messagesContainer.firstChild);
  }
}

function hideWelcomeScreen() {
  const welcomeScreen = document.getElementById('welcomeScreen');
  if (welcomeScreen) {
    welcomeScreen.remove();
  }
}

/**
 * usePrompt(button) — Fills the input with a suggested prompt chip's text.
 * @param {HTMLElement} button - The clicked prompt chip button
 */
function usePrompt(button) {
  el.userInput.value = button.textContent.trim();
  autoResize(el.userInput);
  updateCharCount(el.userInput);
  enableSendButton();
  el.userInput.focus();
}

/**
 * openSourceModal(button) — Opens the source documents modal for a bot message.
 * @param {HTMLElement} button - The "N sources" badge that was clicked
 */
function openSourceModal(button) {
  // Retrieve sources JSON from the data attribute
  let sources;
  try {
    sources = JSON.parse(button.dataset.sources);
  } catch (e) {
    showToast('Could not parse source data', 'error');
    return;
  }

  if (!sources || sources.length === 0) {
    showToast('No source information available', 'info');
    return;
  }

  // Build source card HTML
  el.sourceModalBody.innerHTML = sources.map((src, index) => {
    /*
      src is one source object from the FastAPI response.
      Expected format: { filename, text, score? }
      We handle flexible formats from ChromaDB metadata.
    */
    const filename = src.filename || src.source || src.id || `Chunk ${index + 1}`;
    const text = src.text || src.content || src.page_content || 'No preview available.';
    const score = src.score !== undefined
      ? `Relevance score: ${(src.score * 100).toFixed(1)}%`
      : '';

    return `
      <div class="source-card">
        <div class="source-card-header">
          <div class="source-filename">
            <i class="bi bi-file-earmark-text-fill"></i>
            ${escapeHTML(filename)}
          </div>
          <span class="source-rank">#${index + 1}</span>
        </div>
        <div class="source-text">${escapeHTML(truncateText(text, 300))}</div>
        ${score ? `<div class="source-score"><i class="bi bi-graph-up"></i> ${score}</div>` : ''}
      </div>
    `;
  }).join('');

  // Show Bootstrap modal
  const modal = new bootstrap.Modal(document.getElementById('sourceModal'));
  modal.show();
}

/**
 * copyMessage(button) — Copies the bot's answer text to clipboard.
 * @param {HTMLElement} button - The copy button element
 */
async function copyMessage(button) {
  // Traverse up to find the message-text element
  const messageDiv = button.closest('.message');
  const textEl = messageDiv.querySelector('.message-text');

  if (!textEl) return;

  try {
    await navigator.clipboard.writeText(textEl.textContent);
    /*
      navigator.clipboard.writeText() copies text to the system clipboard.
      It returns a Promise (async operation).
    */

    // Temporarily change button to show success
    const originalHTML = button.innerHTML;
    button.innerHTML = '<i class="bi bi-check-lg"></i> Copied!';
    button.style.color = 'var(--success-color)';

    setTimeout(() => {
      button.innerHTML = originalHTML;
      button.style.color = '';
    }, 2000);
    /*
      setTimeout runs a function after a delay (in ms).
      2000ms = 2 seconds. This resets the button back.
    */

    showToast('Answer copied to clipboard', 'info');
  } catch (e) {
    showToast('Could not copy to clipboard', 'error');
  }
}

/**
 * showToast(message, type) — Shows a temporary notification at bottom-right.
 * @param {string} message - The message to display
 * @param {string} type - 'info' | 'error' | 'success'
 */
function showToast(message, type = 'info') {
  const toastEl = document.getElementById('appToast');

  // Remove previous type classes
  toastEl.classList.remove('toast-success', 'toast-error', 'toast-info');
  toastEl.classList.add(`toast-${type}`);

  el.toastBody.innerHTML = message;

  // Use Bootstrap's Toast API
  const toast = new bootstrap.Toast(toastEl, {
    delay: 3000,      // Auto-dismiss after 3 seconds
    animation: true,
  });
  toast.show();
}

/**
 * disableSendButton() / enableSendButton() — Controls the send button state.
 */
function disableSendButton() {
  el.sendBtn.disabled = true;
  el.sendIcon.className = 'bi bi-hourglass-split';
  /*
    Change icon to hourglass to visually indicate loading state.
  */
}

function enableSendButton() {
  // Only enable if there's actual text in the input
  const hasText = el.userInput.value.trim().length > 0;
  el.sendBtn.disabled = !hasText;
  el.sendIcon.className = 'bi bi-send-fill';
}


/* ================================================================
   11. INPUT HANDLING
   ================================================================ */

/**
 * setupInputListener() — Attaches event listener to the textarea.
 * This enables/disables the send button as user types.
 */
function setupInputListener() {
  el.userInput.addEventListener('input', () => {
    const hasText = el.userInput.value.trim().length > 0;
    el.sendBtn.disabled = !hasText || state.isLoading;
  });
}

/**
 * handleKeyDown(event) — Handles keyboard shortcuts in the textarea.
 * Enter → send message
 * Shift+Enter → new line (default behavior, we don't intercept)
 * @param {KeyboardEvent} event
 */
function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    /*
      event.key === 'Enter' → Enter was pressed
      !event.shiftKey → Shift was NOT held down
      So: Enter alone = send, Shift+Enter = new line
    */
    event.preventDefault();
    /*
      preventDefault() stops the default action.
      Without this, pressing Enter would add a newline AND send.
    */
    sendMessage();
  }
}

/**
 * autoResize(textarea) — Grows the textarea height to fit content.
 * Sets height to 'auto' first to shrink, then to scrollHeight to grow.
 * @param {HTMLTextAreaElement} textarea
 */
function autoResize(textarea) {
  textarea.style.height = 'auto';
  /*
    Setting height to 'auto' first lets the browser recalculate the natural height.
    Without this, the textarea would only grow, never shrink.
  */
  textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px';
  /*
    textarea.scrollHeight = height of all the text content.
    Math.min caps it at 180px (about 8 lines).
    Adding 'px' makes it a valid CSS value.
  */
}

/**
 * updateCharCount(textarea) — Updates the character counter below the input.
 * @param {HTMLTextAreaElement} textarea
 */
function updateCharCount(textarea) {
  const count = textarea.value.length;
  const max = parseInt(textarea.maxLength);   // Gets the maxlength="2000" attribute
  el.charCount.textContent = `${count} / ${max}`;

  // Change color when approaching limit
  el.charCount.classList.remove('warning', 'danger');
  if (count > max * 0.9) {      // Over 90% — red
    el.charCount.classList.add('danger');
  } else if (count > max * 0.7) {  // Over 70% — yellow
    el.charCount.classList.add('warning');
  }
}


/* ================================================================
   12. API HEALTH CHECK
   ================================================================ */

/**
 * checkAPIHealth() — Pings /health endpoint to show online/offline status.
 * Updates the colored dot in the header.
 */
async function checkAPIHealth() {
  try {
    const response = await fetch(`${CONFIG.API_URL}${CONFIG.HEALTH_ENDPOINT}`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
      /*
        AbortSignal.timeout(5000) automatically cancels the request if it takes
        more than 5 seconds. Prevents hanging indefinitely.
      */
    });

    if (response.ok) {
      setAPIStatus('online');
    } else {
      setAPIStatus('offline');
    }
  } catch (e) {
    setAPIStatus('offline');
    /*
      If fetch throws (network error, timeout, CORS), the API is unreachable.
    */
  }
}

/**
 * setAPIStatus(status) — Updates the status indicator UI.
 * @param {string} status - 'online' | 'offline' | 'checking'
 */
function setAPIStatus(status) {
  el.statusDot.className = 'status-dot';   // Reset classes

  switch (status) {
    case 'online':
      el.statusDot.classList.add('online');
      el.statusText.textContent = 'Connected';
      break;
    case 'offline':
      el.statusDot.classList.add('offline');
      el.statusText.textContent = 'Offline';
      break;
    default:
      el.statusText.textContent = 'Checking...';
  }
}


/* ================================================================
   HELPER / FORMAT FUNCTIONS
   ================================================================ */

/**
 * generateId() — Creates a unique ID string.
 * Used for chat IDs and typing indicator IDs.
 * @returns {string}
 */
function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
  /*
    Date.now().toString(36) → timestamp in base-36 (shorter string)
    Math.random().toString(36).substr(2, 5) → 5 random alphanumeric chars
    Combined: something like "lc7x3abcd" — practically unique
  */
}

/**
 * formatTime(date) — Formats a Date object to "HH:MM AM/PM".
 * @param {Date} date
 * @returns {string}
 */
function formatTime(date) {
  if (!(date instanceof Date)) {
    date = new Date(date);    // Handle ISO string from localStorage
  }
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    /*
      'en-IN' = Indian English locale (12-hour format with AM/PM).
      Since you're in Kerala, this is appropriate.
    */
  });
}

/**
 * formatMessageContent(content) — Safely formats message text for HTML display.
 * Escapes HTML special characters, then applies formatting.
 * @param {string} content
 * @returns {string} HTML string
 */
function formatMessageContent(content) {
  // First, escape HTML to prevent XSS (security: don't render user/API HTML)
  let safe = escapeHTML(content);

  // Then apply our own formatting:

  // Inline code: `code` → <code>code</code>
  safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold: **text** → <strong>text</strong>
  safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // URLs: Make clickable (safe because we already escaped HTML)
  safe = safe.replace(
    /(https?:\/\/[^\s<>"{}|\\^`[\]]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:var(--accent)">$1</a>'
  );
  /*
    target="_blank" → opens in new tab
    rel="noopener noreferrer" → security: prevents the new tab from accessing our page
  */

  return safe;
}

/**
 * escapeHTML(str) — Converts HTML special characters to entities.
 * CRITICAL for security: prevents XSS (cross-site scripting) attacks.
 * If user types "<script>alert('hack')</script>", we show the text, not execute the script.
 * @param {string} str
 * @returns {string}
 */
function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * escapeJSON(obj) — Converts an object to a JSON string safe for HTML attributes.
 * @param {any} obj
 * @returns {string}
 */
function escapeJSON(obj) {
  return JSON.stringify(obj).replace(/'/g, '&#039;');
  /*
    We store JSON in data-sources='...' attribute.
    Single quotes in JSON would break the attribute.
  */
}

/**
 * truncateText(text, maxLength) — Truncates text with ellipsis.
 * @param {string} text
 * @param {number} maxLength
 * @returns {string}
 */
function truncateText(text, maxLength) {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}

/**
 * formatErrorMessage(error) — Returns user-friendly error message.
 * @param {Error} error
 * @returns {string}
 */
function formatErrorMessage(error) {
  if (error instanceof APIError) {
    if (error.status === 422) {
      return '⚠️ The API could not process that request. Please try rephrasing your question.';
    }
    if (error.status === 500) {
      return '⚠️ The AI service encountered an internal error. Please try again in a moment.';
    }
    if (error.status === 404) {
      return '⚠️ The chat endpoint was not found. Please check your FastAPI server configuration.';
    }
    return `⚠️ API Error: ${error.message}`;
  }

  if (error.name === 'TypeError' && error.message.includes('fetch')) {
    return '⚠️ Could not connect to the Sahachari API. Make sure your FastAPI server is running on port 8000.\n\n💡 Run: uvicorn main:app --reload';
  }

  return `⚠️ An unexpected error occurred: ${error.message}`;
}

/**
 * getErrorToastMessage(error) — Short message for toast notification.
 */
function getErrorToastMessage(error) {
  if (error.name === 'TypeError') return '🔴 API connection failed';
  if (error instanceof APIError && error.status >= 500) return '🔴 Server error';
  return '🔴 Request failed';
}


/* ================================================================
   CUSTOM ERROR CLASS
   ================================================================
  We create a custom Error class so we can attach extra data (like status code).
  This helps format error messages more specifically.
*/

class APIError extends Error {
  constructor(message, status) {
    super(message);
    /*
      super() calls the parent class (Error) constructor.
      This sets this.message = message.
    */
    this.name = 'APIError';
    this.status = status;
    /*
      Now we can check: if (error.status === 500) ...
    */
  }
}


/* ================================================================
   MAKE FUNCTIONS GLOBAL
   ================================================================
  Functions called from HTML onclick="..." must be on the window object (globally accessible).
  Functions defined inside modules or with certain patterns may not be global by default.
  We explicitly assign them to window to be safe.
*/

window.sendMessage     = sendMessage;
window.startNewChat    = startNewChat;
window.loadChat        = loadChat;
window.toggleTheme     = toggleTheme;
window.openSidebar     = openSidebar;
window.closeSidebar    = closeSidebar;
window.clearCurrentChat = clearCurrentChat;
window.copyMessage     = copyMessage;
window.openSourceModal = openSourceModal;
window.usePrompt       = usePrompt;
window.handleKeyDown   = handleKeyDown;
window.autoResize      = autoResize;
window.updateCharCount = updateCharCount;