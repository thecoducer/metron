/* Metron - Reusable Pagination Component */

class PaginationManager {
  constructor(pageSize = 10, currentPage = 1) {
    this.pageSize = pageSize;
    this.currentPage = currentPage;
  }

  /**
   * Change page size and reset to first page
   */
  changePageSize(size) {
    this.pageSize = parseInt(size);
    this.currentPage = 1;
  }

  /**
   * Navigate to a specific page
   */
  goToPage(page) {
    this.currentPage = page;
  }

  /**
   * Calculate pagination data for a dataset
   * @param {Array} data - Complete dataset
   * @returns {Object} Pagination info and sliced data
   */
  paginate(data) {
    const totalItems = data.length;
    const effectivePageSize = this.pageSize === 100 ? totalItems : this.pageSize;
    const totalPages = Math.ceil(totalItems / effectivePageSize) || 1;
    const currentPage = Math.min(this.currentPage, totalPages);
    
    const startIndex = (currentPage - 1) * effectivePageSize;
    const endIndex = Math.min(startIndex + effectivePageSize, totalItems);
    const pageData = data.slice(startIndex, endIndex);

    return {
      pageData,
      totalItems,
      totalPages,
      currentPage,
      startIndex,
      endIndex,
      pageSize: effectivePageSize
    };
  }

  /**
   * Build pagination buttons HTML
   * @param {number} currentPage - Current page number
   * @param {number} totalPages - Total number of pages
   * @param {string} clickFunctionName - Name of the global click handler function
   * @param {number} maxPageButtons - Maximum page buttons to show (default: 5)
   * @returns {string} HTML for pagination buttons
   */
  static buildPaginationButtons(currentPage, totalPages, clickFunctionName, maxPageButtons = 5) {
    if (totalPages <= 1) {
      return '';
    }

    let buttonsHTML = '';

    // Page number buttons
    let startPage = Math.max(1, currentPage - Math.floor(maxPageButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxPageButtons - 1);
    
    if (endPage - startPage < maxPageButtons - 1) {
      startPage = Math.max(1, endPage - maxPageButtons + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      const activeClass = i === currentPage ? 'active' : '';
      buttonsHTML += `<button class="${activeClass}" onclick="window.${clickFunctionName}(${i})">${i}</button>`;
    }

    return buttonsHTML;
  }

  /**
   * Update pagination UI elements
   * @param {Object} paginationInfo - Info from paginate() method
   * @param {string} infoElementId - ID of info display element
   * @param {string} buttonsElementId - ID of buttons container element
   * @param {string} clickFunctionName - Name of the global click handler function
   * @param {string} itemName - Name of items being paginated (e.g., 'stocks', 'items')
   */
  static updatePaginationUI(paginationInfo, infoElementId, buttonsElementId, clickFunctionName, itemName = 'items') {
    const infoDiv = document.getElementById(infoElementId);
    const buttonsDiv = document.getElementById(buttonsElementId);
    
    if (!infoDiv || !buttonsDiv) return;

    const { totalItems, currentPage, startIndex, endIndex } = paginationInfo;

    // Update info text
    if (totalItems > 0) {
      infoDiv.textContent = `Showing ${startIndex + 1}-${endIndex} of ${totalItems} ${itemName}`;
    } else {
      infoDiv.innerHTML = '<span class="loading-dots">Loading data</span>';
    }

    // Update buttons
    buttonsDiv.innerHTML = this.buildPaginationButtons(
      currentPage,
      paginationInfo.totalPages,
      clickFunctionName
    );
  }
}

export default PaginationManager;
