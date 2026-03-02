/* Metron - Server-Sent Events (SSE) Connection Manager */

class SSEConnectionManager {
  constructor(eventUrl = '/events', reconnectDelay = 5000) {
    this.eventUrl = eventUrl;
    this.reconnectDelay = reconnectDelay;
    this.eventSource = null;
    this.messageHandlers = [];
    this.errorHandlers = [];
    this.openHandlers = [];
  }

  /**
   * Add a message handler callback
   * @param {Function} handler - Callback function that receives parsed event data
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
  }

  /**
   * Add an error handler callback
   * @param {Function} handler - Callback function that receives error event
   */
  onError(handler) {
    this.errorHandlers.push(handler);
  }

  /**
   * Add an open handler callback
   * @param {Function} handler - Callback function called when connection opens
   */
  onOpen(handler) {
    this.openHandlers.push(handler);
  }

  /**
   * Connect to the SSE endpoint
   */
  connect() {
    // Close existing connection if any
    if (this.eventSource) {
      this.eventSource.close();
    }

    // Create new EventSource connection
    this.eventSource = new EventSource(this.eventUrl);

    // Handle incoming messages
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[SSEManager] Received SSE message:', data);
        this.messageHandlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error('Error in SSE message handler:', error);
          }
        });
      } catch (error) {
        console.error('Error parsing SSE message:', error);
      }
    };

    // Handle errors
    this.eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      
      this.errorHandlers.forEach(handler => {
        try {
          handler(error);
        } catch (err) {
          console.error('Error in SSE error handler:', err);
        }
      });

      // Attempt to reconnect after delay if connection is closed
      if (this.eventSource.readyState === EventSource.CLOSED) {
        console.log(`Reconnecting to SSE in ${this.reconnectDelay / 1000}s...`);
        setTimeout(() => this.connect(), this.reconnectDelay);
      }
    };

    // Handle connection open
    this.eventSource.onopen = () => {
      console.log('SSE connection established');
      this.openHandlers.forEach(handler => {
        try {
          handler();
        } catch (error) {
          console.error('Error in SSE open handler:', error);
        }
      });
    };
  }

  /**
   * Disconnect from the SSE endpoint
   */
  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
      console.log('SSE connection closed');
    }
  }

  /**
   * Check if currently connected
   * @returns {boolean} True if connected
   */
  isConnected() {
    return this.eventSource && this.eventSource.readyState === EventSource.OPEN;
  }

  /**
   * Clear all handlers
   */
  clearHandlers() {
    this.messageHandlers = [];
    this.errorHandlers = [];
    this.openHandlers = [];
  }
}

export default SSEConnectionManager;
