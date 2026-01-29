# CIP Weekly Digest - Mermaid Diagrams

Copy these diagrams to any Mermaid-compatible viewer (GitHub, Notion, Confluence, etc.)

---

## 1. Overall System Architecture

```mermaid
flowchart LR
    subgraph Input["📥 Input"]
        CONF[("Confluence")]
    end
    
    subgraph Triggers["⚡ Triggers"]
        TIMER[/"Timer"/]
        HTTP[/"HTTP"/]
    end
    
    subgraph Pipeline["🔧 Processing Pipeline"]
        direction TB
        DETECT["Change Detector"]
        EXTRACT["Content Extractor"]
        IMAGE["Image Processor"]
        INDEX["Search Indexer"]
        EMAILGEN["Email Generator"]
    end
    
    subgraph AI["🤖 AI"]
        GPT["GPT-4o"]
        EMB["Embeddings"]
    end
    
    subgraph Storage["💾 Storage"]
        BLOB[("Blob")]
        SEARCH[("AI Search")]
        COSMOS[("Cosmos DB")]
    end
    
    subgraph Output["📤 Output"]
        LOGIC["Logic App"]
        O365[("Office 365")]
    end
    
    subgraph UI["🖥️ UI"]
        STREAM["Streamlit"]
    end

    %% Main Flow
    TIMER & HTTP --> DETECT
    CONF --> DETECT
    DETECT --> EXTRACT
    EXTRACT --> IMAGE
    IMAGE --> INDEX
    INDEX --> EMAILGEN
    
    %% AI Connections
    IMAGE --> GPT
    INDEX --> EMB
    EMAILGEN --> GPT
    
    %% Storage Connections
    DETECT --> BLOB
    INDEX --> SEARCH
    EMAILGEN --> COSMOS
    
    %% Output Flow
    EMAILGEN --> LOGIC
    LOGIC --> O365
    
    %% UI Flow
    STREAM --> COSMOS
    
    classDef input fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    classDef trigger fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    classDef pipeline fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    classDef ai fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    classDef storage fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    classDef output fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    classDef ui fill:#d4b8ff,stroke:#a67bd9,color:#3b1a5c
    
    class CONF input
    class TIMER,HTTP trigger
    class DETECT,EXTRACT,IMAGE,INDEX,EMAILGEN pipeline
    class GPT,EMB ai
    class BLOB,SEARCH,COSMOS storage
    class LOGIC,O365 output
    class STREAM ui
```

---

## 2. Complete Pipeline Flow (Sequence)

```mermaid
sequenceDiagram
    autonumber
    participant Timer as Timer Trigger
    participant Orch as Orchestrator
    participant Conf as Confluence
    participant Blob as Blob Storage
    participant GPT as GPT-4o
    participant Search as AI Search
    participant Cosmos as Cosmos DB
    participant Logic as Logic App
    participant Email as Office 365

    Timer->>Orch: Trigger (every 5 min)
    
    rect rgb(239, 246, 255)
        Note over Orch,Blob: Change Detection
        Orch->>Conf: Fetch page content
        Conf-->>Orch: HTML + version
        Orch->>Blob: Get stored hash
        Blob-->>Orch: Previous hash
        Orch->>Orch: Compare hashes
    end
    
    alt Changes Detected
        rect rgb(236, 253, 245)
            Note over Orch,Blob: Content Processing
            Orch->>Conf: Extract full content
            Conf-->>Orch: Structured content
            Orch->>GPT: Describe images
            GPT-->>Orch: Image descriptions
            Orch->>Blob: Upload content
        end
        
        rect rgb(254, 249, 195)
            Note over Orch,Search: Search Indexing
            Orch->>GPT: Generate embeddings
            GPT-->>Orch: Vectors
            Orch->>Search: Index chunks
        end
        
        rect rgb(243, 232, 255)
            Note over Orch,Email: Email Delivery
            Orch->>Search: Query context
            Search-->>Orch: Relevant chunks
            Orch->>GPT: Generate summary
            GPT-->>Orch: Email content
            Orch->>Cosmos: Get subscribers
            Cosmos-->>Orch: Email list
            Orch->>Logic: Send emails
            Logic->>Email: Deliver
        end
    else No Changes
        Orch->>Orch: Skip processing
    end
```

---

## 3. Change Detection Flow

```mermaid
flowchart LR
    A[Start] --> B[Fetch Page]
    B --> C[Extract Text]
    C --> D[Calculate Hash]
    D --> E{Previous Hash?}
    E -->|No| F[First Run]
    E -->|Yes| G{Match?}
    G -->|Yes| H[No Changes]
    G -->|No| I[Changes Found]
    F --> I
    I --> J[Save Hash]
    
    style A fill:#e8f0fe,stroke:#a8d5ff,color:#1a365d
    style I fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style H fill:#e0e0e0,stroke:#b0b0b0,color:#404040
    style J fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style F fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
```

---

## 4. Email Generation Flow

```mermaid
flowchart TB
    A[Page Changed] --> B[Query AI Search]
    B --> C[Build Prompt]
    C --> D[Call GPT-4o]
    D --> E[Format HTML]
    E --> F[Upload to Blob]
    F --> G[Get Subscribers]
    G --> H{Has Subscribers?}
    H -->|No| I[Log & Skip]
    H -->|Yes| J[For Each User]
    J --> K[Call Logic App]
    K --> L[Send via O365]
    L --> M[Delivered]
    
    style A fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    style D fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style M fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style I fill:#e0e0e0,stroke:#b0b0b0,color:#404040
    style F fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
```

---

## 5. Subscription Management Flow

```mermaid
flowchart LR
    subgraph Streamlit["Streamlit Portal"]
        UI[User Interface]
    end
    
    subgraph CosmosDB["Cosmos DB"]
        SUBS[(subscriptions)]
    end
    
    UI -->|Subscribe| A[Create/Update]
    UI -->|Load| B[Get Settings]
    UI -->|Unsubscribe| C[Delete]
    
    A --> SUBS
    B --> SUBS
    C --> SUBS
    
    subgraph AzureFunctions["Azure Functions"]
        NOTIFY[Email Sender]
    end
    
    NOTIFY -->|Query| SUBS
    SUBS -->|Return| NOTIFY
    
    style UI fill:#d4b8ff,stroke:#a67bd9,color:#3b1a5c
    style SUBS fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style NOTIFY fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style A fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style C fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
```

---

## 6. Data Storage Architecture

```mermaid
flowchart LR
    subgraph BlobStorage["Azure Blob Storage"]
        direction TB
        subgraph state["confluence-state"]
            S1["version.json"]
            S2["history/"]
        end
        
        subgraph rag["confluence-rag"]
            R1["document.json"]
        end
        
        subgraph media["confluence-media"]
            M1["images/"]
        end
        
        subgraph emails["confluence-emails"]
            E1["latest/"]
            E2["archive/"]
        end
    end
    
    subgraph SearchIndex["Azure AI Search"]
        direction TB
        IDX[("confluence-rag-index")]
        IDX --> C1["chunk_0"]
        IDX --> C2["chunk_1"]
        IDX --> C3["chunk_n"]
    end
    
    subgraph CosmosDB["Cosmos DB"]
        direction TB
        DB[("confluence-digest")]
        DB --> CONT[("subscriptions")]
    end
    
    %% Blob Storage styles
    style BlobStorage fill:#fff5e6,stroke:#d9b86b
    style state fill:#ffe8b8,stroke:#d9b86b
    style rag fill:#ffe8b8,stroke:#d9b86b
    style media fill:#ffe8b8,stroke:#d9b86b
    style emails fill:#ffe8b8,stroke:#d9b86b
    style S1 fill:#fff,stroke:#d9b86b,color:#5c4813
    style S2 fill:#fff,stroke:#d9b86b,color:#5c4813
    style R1 fill:#fff,stroke:#d9b86b,color:#5c4813
    style M1 fill:#fff,stroke:#d9b86b,color:#5c4813
    style E1 fill:#fff,stroke:#d9b86b,color:#5c4813
    style E2 fill:#fff,stroke:#d9b86b,color:#5c4813
    
    %% Search Index styles
    style SearchIndex fill:#e6f3ff,stroke:#5ba3d9
    style IDX fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style C1 fill:#fff,stroke:#5ba3d9,color:#1a365d
    style C2 fill:#fff,stroke:#5ba3d9,color:#1a365d
    style C3 fill:#fff,stroke:#5ba3d9,color:#1a365d
    
    %% Cosmos DB styles
    style CosmosDB fill:#e6f5e6,stroke:#7bc47b
    style DB fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style CONT fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
```

---

## 7. Technology Stack

```mermaid
mindmap
  root((CIP Digest))
    Backend
      Azure Functions
        Python 3.11
        Timer Trigger
        HTTP Trigger
      Modules
        Change Detector
        Content Extractor
        Image Processor
        Search Indexer
        Email Generator
        Email Sender
    AI/ML
      Azure OpenAI
        GPT-4o
        Embeddings
      Vector Search
        HNSW
        1536 dims
    Storage
      Blob Storage
        state
        rag
        media
        emails
      Cosmos DB
        subscriptions
      AI Search
        rag-index
    Email
      Logic Apps
      Office 365
    Frontend
      Streamlit Cloud
```

---

## 8. Component Interaction

```mermaid
graph TB
    subgraph Triggers["Triggers"]
        T1[Timer]
        T2[HTTP]
    end
    
    subgraph Core["Processing"]
        C1[Monitor]
        C2[Extractor]
        C3[Image AI]
        C4[Uploader]
        C5[Indexer]
        C6[Email Gen]
        C7[Sender]
        C8[Subscriptions]
    end
    
    subgraph External["External"]
        E1[Confluence]
        E2[OpenAI]
        E3[Logic App]
    end
    
    subgraph Azure["Azure"]
        A1[(Blob)]
        A2[(Cosmos)]
        A3[(Search)]
    end
    
    T1 & T2 --> C1
    C1 --> E1
    C1 --> A1
    C1 --> C2
    C2 --> E1
    C2 --> C3
    C3 --> E2
    C3 --> A1
    C2 --> C4
    C4 --> A1
    C4 --> C5
    C5 --> E2
    C5 --> A3
    C6 --> E2
    C6 --> A3
    C6 --> A1
    C7 --> E3
    C7 --> C8
    C8 --> A2
    
    style T1 fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style T2 fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style E1 fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    style E2 fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style E3 fill:#d4b8ff,stroke:#a67bd9,color:#3b1a5c
    style A1 fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style A2 fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style A3 fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
```

---

## 9. Deployment Architecture

```mermaid
flowchart TB
    subgraph GitHub["GitHub"]
        REPO[Repository]
    end
    
    subgraph Azure["Azure"]
        FUNC[Azure Functions]
        LOGIC[Logic App]
        BLOB[(Blob Storage)]
        COSMOS[(Cosmos DB)]
        SEARCH[(AI Search)]
        OPENAI[OpenAI]
    end
    
    subgraph Streamlit["Streamlit Cloud"]
        PORTAL[Portal]
    end
    
    subgraph External["External"]
        CONF[Confluence]
        O365[Office 365]
    end
    
    REPO -->|Deploy| FUNC
    REPO -->|Deploy| PORTAL
    
    FUNC --> CONF
    FUNC --> BLOB
    FUNC --> COSMOS
    FUNC --> SEARCH
    FUNC --> OPENAI
    FUNC --> LOGIC
    LOGIC --> O365
    
    PORTAL --> COSMOS
    
    style FUNC fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
    style PORTAL fill:#d4b8ff,stroke:#a67bd9,color:#3b1a5c
    style OPENAI fill:#b8e6b8,stroke:#7bc47b,color:#1e4620
    style CONF fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    style O365 fill:#ffb8b8,stroke:#d98b8b,color:#7c2d2d
    style BLOB fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style COSMOS fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style SEARCH fill:#ffe8b8,stroke:#d9b86b,color:#5c4813
    style LOGIC fill:#a8d5ff,stroke:#5ba3d9,color:#1a365d
```

---

## Color Legend

| Color | Hex | Usage |
|-------|-----|-------|
| 🔵 Soft Blue | `#a8d5ff` | Azure Functions / Core Processing |
| 🔴 Soft Red | `#ffb8b8` | External Systems (Confluence, O365) |
| 🟢 Soft Green | `#b8e6b8` | AI Services (GPT-4o, Embeddings) |
| 🟠 Soft Orange | `#ffe8b8` | Storage (Blob, Cosmos, Search) |
| 🟣 Soft Purple | `#d4b8ff` | Frontend (Streamlit) |
| ⚪ Light Gray | `#e8f0fe` | Neutral / Start nodes |

---

*Use these diagrams in GitHub README, Confluence, Notion, or any Mermaid-compatible viewer.*
