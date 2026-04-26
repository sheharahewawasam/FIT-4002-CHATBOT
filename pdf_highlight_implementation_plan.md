# Implementation Plan: PDF Highlight-in-Context Strategy

This document outlines the architectural and procedural transition from standard source-document linking to a high-precision "Highlight-in-Context" feature for the Project 26 Advisor Chatbot.

---

## 1. Project Objective
To enhance advisor trust and efficiency by visually pinpointing the exact location of supporting evidence within fund documentation. Instead of providing a generic link to a multi-page PDF, the system will automatically navigate to and highlight the specific paragraph or table used by the AI.

---

## 2. Architectural Transformation
To achieve precise highlighting, the system must shift from a "text-only" retrieval model to a "coordinate-aware" spatial model.

### 2.1 The Coordinate-Aware Pipeline
The system must be redesigned to treat spatial data as a first-class citizen alongside text.
* **Spatial Ingestion:** The ingestion process must capture the "Bounding Box" (BBox) of every text segment. This BBox consists of numerical coordinates representing the physical area the text occupies on a page.
* **Metadata Enrichment:** Every document "node" in the vector database will be enriched with specific metadata: Source URL, Page Number, and BBox coordinates (X, Y, Width, and Height).

---

## 3. Implementation Phases

### Phase 1: Ingestion & Data Preparation
The initial document processing must be upgraded to extract layout information.
* **Layout Parsing:** The system identifies text blocks and records their position relative to the page margins.
* **Coordinate Storage:** These coordinates are stored in the Vector Database (MongoDB Atlas) alongside the semantic embeddings. This ensures that when a text chunk is retrieved, its physical location is retrieved with it.

### Phase 2: Retrieval & Response Mapping
The orchestration layer must ensure the relationship between the AI's answer and the physical document is preserved.
* **Citation Mapping:** For every claim the AI makes, the backend identifies the unique ID of the source text chunk.
* **Spatial Packaging:** The API response sent to the dashboard will now include a "Spatial Signature" for each citation, containing the URL, page, and coordinate set.

### Phase 3: Frontend Integration (The Advisor Dashboard)
The user interface in the Apex dashboard will be updated to handle interactive document viewing.
* **Split-Pane Interface:** The UI will adopt a side-by-side layout. The chat remains on the left, while a dedicated PDF viewer occupies the right.
* **Interaction Logic:** When an advisor clicks a citation in the chat, the PDF viewer will instantly scroll to the correct page and render a semi-transparent highlight overlaying the specific coordinates provided by the API.

---

## 4. Handling Legacy & Scanned Documents
A significant portion of the client's documents are image-based scans. 
* **Spatial OCR:** The internal OCR pipeline must be configured to return coordinate data for every recognized word.
* **Layer Alignment:** For these documents, the system will overlay the highlight on top of the image layer using the coordinates generated during the OCR phase.

---

## 5. Quality Assurance & Accuracy
* **Visual Calibration:** Testing will ensure that highlights align perfectly with the text across various zoom levels and screen resolutions.
* **Citation Verification:** The system will undergo rigorous "Precision Audits" to ensure the AI is highlighting the specific rule it is quoting, not just a nearby paragraph.

---
**Author:** Shehara Hewawasam
**Role:** Software Architect
**Date:** April 21, 2026
