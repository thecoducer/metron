/* Metron - Server-Sent Events (SSE) Connection Manager */

class SSEConnectionManager {
  constructor(eventUrl = '/events', reconnectDelay = 5000) {
    this.eventUrl = eventUrl;
    this.reconnectDelay = reconnectDelay;
    this.eventSource = null;
    this.messageHandlers = [];
  }

  /**
   * Add a message handler callback
   * @param {Function} handler - Callback function that receives parsed event data
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
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

      // Attempt to reconnect after delay if connection is closed
      if (this.eventSource.readyState === EventSource.CLOSED) {
        console.log(`Reconnecting to SSE in ${this.reconnectDelay / 1000}s...`);
        setTimeout(() => this.connect(), this.reconnectDelay);
      }
    };

    // Handle connection open
    this.eventSource.onopen = () => {
      console.log('SSE connection established');
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
}

export default SSEConnectionManager;
