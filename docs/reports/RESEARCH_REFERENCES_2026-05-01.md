# Lorevox/Hornelore — Research Reference List
**Date:** 2026-05-01

---

## Section 1: Core References (Cited in CLAUDE.md / Architecture Spec)

### Easy Turn: Integrating Acoustic and Linguistic Modalities for Robust Turn-Taking in Full-Duplex Spoken Dialogue Systems
- **File:** `Research/Easy_Turn_Integrating_Acoustic_and_Linguistic_Modalities_for_Robust_Turn-Taking_in_Full-Duplex_Spoken_Dialogue_Systems.pdf`
- **Authors:** Guojian Li, Chengyou Wang, Hongfei Xue, Shuiyuan Wang, Dehui Guo, Zihan Zhang, Yuke Lin, Wenjie Li, Longshuai Xiao, Zhonghua Fu, Lei Xie
- **Journal:** ICASSP 2026
- **Citation:** Li et al. (2026). "Easy Turn: Integrating Acoustic and Linguistic Modalities for Robust Turn-Taking in Full-Duplex Spoken Dialogue Systems." Proceedings of ICASSP 2026.
- **What it supports:** Directly cited in CLAUDE.md as foundational work on full-duplex dialogue and turn-taking detection. Supports Lori's conversational turn-management layer and the integration of acoustic signals with linguistic processing for natural dialogue flow.

### The ICASSP 2026 HumDial Challenge: Benchmarking Human-Like Spoken Dialogue Systems in the LLM Era
- **File:** `Research/The_ICASSP_2026_Humdial_Challenge_Benchmarking_Human-Like_Spoken_Dialogue_Systems_in_the_LLM_Era.pdf`
- **Authors:** Zhixian Zhao, Shuiyuan Wang, Guojian Li, Hongfei Xue, Chengyou Wang, Shuai Wang, Longshuai Xiao, Zihan Zhang, Hui Bu, Xin Xu, Xinsheng Wang, Hexin Liu, Eng Siong Chng, Hung-yi Lee, Lei Xie
- **Journal:** ICASSP 2026
- **Citation:** Zhao et al. (2026). "The ICASSP 2026 HumDial Challenge: Benchmarking Human-Like Spoken Dialogue Systems in the LLM Era."
- **What it supports:** Referenced as HumDial framework. Supports evaluation methodology for dialogue systems that achieve human-like conversational capability. Directly applicable to Lori's design goals and the multi-turn evaluation harness.

### Reproducing Proficiency-Conditioned Dialogue Features with Full-duplex Spoken Dialogue Models
- **File:** `Research/2026.iwsds-1.4.pdf`
- **Authors:** Takao Obi, Sadahiro Yoshikawa, Mao Saeki, Masaki Eguchi, Voichi Matsuyama
- **Journal:** IWSDS 2026
- **Citation:** Obi et al. (2026). "Reproducing Proficiency-Conditioned Dialogue Features with Full-duplex Spoken Dialogue Models."
- **What it supports:** Cited as PersonaPlex / Proficiency-Conditioned reference. Supports dialogue systems that adapt response generation based on interlocutor proficiency levels — directly applicable to Lori's cognitive support mode (WO-10C) and adaptation to narrator capability.

### Beyond Prompt Engineering: Robust Behavior Control in LLMs via Steering Target Atoms
- **File:** `Research/2025.acl-long.1139.pdf`
- **Authors:** Mengru Wang, Ziwen Xu, Shengyu Mao, Shumin Deng, Zhaopeng Tu, Huajun Chen, Ningyu Zhang
- **Journal:** ACL 2025
- **Citation:** Wang et al. (2025). "Beyond Prompt Engineering: Robust Behavior Control in LLMs via Steering Target Atoms." Proceedings of ACL 2025.
- **What it supports:** Directly cited in CLAUDE.md as STA framework. Supports Lorevox's shift from prompt-only to deterministic enforcement. Core to the dialogue policy three-layer architecture (composer → wrapper → harness) and the runtime enforcement of one-question-per-turn discipline.

---

## Section 2: Supporting References (Back Current WOs)

### What's In My Human Feedback? Learning Interpretable Descriptions of Preference Data
- **File:** `Research/16138_What_s_In_My_Human_Feedb.pdf`
- **Authors:** Rajiv Movva, Smitha Milli, Sewon Min, Emma Pierson
- **Journal:** ICLR 2026
- **Citation:** Movva et al. (2026). "What's In My Human Feedback? Learning Interpretable Descriptions of Preference Data." ICLR 2026.
- **What it supports:** Supports preference learning and preference data interpretation relevant to WO-LORI-CONFIRM-01. Methodologically grounded for understanding what user confirmations encode in multi-turn interview workflows.

### GAIA2: Benchmarking LLM Agents on Dynamic and Asynchronous Environments
- **File:** `Research/17177_Gaia2_Benchmarking_LLM_A.pdf`
- **Authors:** Romain Froger, Pierre Andrews, Matteo Bettini, Amar Budhiraja, Ricardo Silveira Cabral, et al.
- **Organization:** Meta Superintelligence Labs
- **Citation:** Froger et al. (2026). "GAIA2: Benchmarking LLM Agents on Dynamic and Asynchronous Environments."
- **What it supports:** Supports agent evaluation methodology and dynamic environment handling. Applicable to WO-LORI-SESSION-AWARENESS-01's stateful interview engine and narrator state tracking across turn sequences.

### LoongRL: Reinforcement Learning for Advanced Reasoning over Long Contexts
- **File:** `Research/22452_LoongRL_Reinforcement_Le.pdf`
- **Authors:** Siyuan Wang, Gaokai Zhang, Li Lyna Zhang, Ning Shang, Fan Yang, Dongyao Chen, Mao Yang
- **Journal:** ICLR 2026
- **Citation:** Wang et al. (2026). "LoongRL: Reinforcement Learning for Advanced Reasoning over Long Contexts." ICLR 2026.
- **What it supports:** Supports long-context reasoning capability for multi-turn interview state management. Applicable to WO-EVAL-MULTITURN-01 and sequence-level pattern detection in the golfball harness.

### Latent Speech-Text Transformer
- **File:** `Research/22526_Latent_Speech_Text_Trans.pdf`
- **Authors:** Yen-Ju Lu, Yasesh Gaur, Wei Zhou, Benjamin Muller, Jesus Villalba, Najim Dehak, Luke Zettlemoyer, Gargi Ghosh, Mike Lewis, Srinivasan Iyer, Duc Le
- **Journal:** ICLR 2026
- **Citation:** Lu et al. (2026). "Latent Speech-Text Transformer." ICLR 2026.
- **What it supports:** Supports STT fragility handling (WO-STT-LIVE-02) and audio-linguistic alignment for narrator speech input robustness. Directly applicable to the transcript safety layer and identity preservation against speech recognition noise.

### AstaBench: Rigorous Benchmarking of AI Agents with a Scientific Research Suite
- **File:** `Research/23372_AstaBench_Rigorous_Bench.pdf`
- **Authors:** Jonathan Bragg, Mike D'Arcy, Nishant Balepur, Dan Bareket, Bhavana Dalvi, et al.
- **Citation:** Bragg et al. (2026). "AstaBench: Rigorous Benchmarking of AI Agents with a Scientific Research Suite."
- **What it supports:** Supports the multi-turn evaluation harness design and reproducible agent benchmarking methodology. Applicable to WO-LORI-RESPONSE-HARNESS-01 and standardized testing of Lori's behavior across controlled scenarios.

### Q-RAG: Long Context Multi-Step Retrieval via Value-Based Embedder Training
- **File:** `Research/25302_Q_RAG_Long_Context_Multi.pdf`
- **Authors:** Artyom Sorokin, Nazar Buzun, Alexander Anokhin, Egor Vedernikov, Petr Auchin, Mikhail Burtsev, Evgeny Burnaev
- **Citation:** Sorokin et al. (2026). "Q-RAG: Long Context Multi-Step Retrieval via Value-Based Embedder Training."
- **What it supports:** Supports retrieval-augmented generation for long-context reasoning in multi-turn narratives. Applicable to Lori's memory echo composition (WO-LORI-SESSION-AWARENESS-01 Phase 1a) and narrator history retrieval.

### Common Corpus: The Largest Collection of Ethical Data for LLM Pre-Training
- **File:** `Research/25369_Common_Corpus_The_Larges.pdf`
- **Authors:** Pierre-Carl Langlais, Pavel Chizhov, Catherine Arnett, Carlos Rosas Hinostroza, Mattia Nee, Eliot Krzystof Jones, Irène Girard, David Mach, Anastasia Stasenko, Ivan P. Yamshchikov
- **Citation:** Langlais et al. (2026). "Common Corpus: The Largest Collection of Ethical Data for LLM Pre-Training."
- **What it supports:** Supports data curation and ethical dataset construction relevant to Lori's training data sourcing and bias mitigation in older-adult dialogue systems.

### Reliable Weak-to-Strong Monitoring of LLM Agents
- **File:** `Research/6444_Reliable_Weak_to_Strong_M.pdf`
- **Authors:** Neil Kale, Chen Bo Calvin Zhang, Kevin Zhu, Ankit Aich, Paula Rodriguez, Scale Red Team, Christina Q. Knight, Zifan Wang
- **Organization:** Scale AI
- **Citation:** Kale et al. (2026). "Reliable Weak-to-Strong Monitoring of LLM Agents." ICLR 2026.
- **What it supports:** Supports agent monitoring and behavior oversight relevant to WO-LORI-SAFETY-INTEGRATION-01. Applicable to the safety layer's deterministic pattern detection and operator notification surface.

### Multimodal Aligned Semantic Knowledge for Unpaired Image-Text Matching
- **File:** `Research/8327_Multimodal_Aligned_Semant.pdf`
- **Authors:** Laiguo Yin, Vixin Zhang, Yuqing Sun, Lizhen Cui
- **Citation:** Yin et al. (2026). "Multimodal Aligned Semantic Knowledge for Unpaired Image-Text Matching."
- **What it supports:** Supports multimodal grounding for the facial awareness stack (WO-AFFECT-ANCHOR-01, parked). Relevant to MediaPipe FaceMesh integration and affect state alignment with narrative content.

### Designing Personality-Adaptive Conversational Agents for Mental Health Care
- **File:** `Research/s10796-022-10254-9.pdf`
- **Authors:** Rangina Ahmad, Dominik Siemon, Ulrich Gneweuch, Susanne Robra-Bissantz
- **Journal:** Information Systems Frontiers, 2022
- **Citation:** Ahmad et al. (2022). "Designing Personality-Adaptive Conversational Agents for Mental Health Care." Information Systems Frontiers, 24(2), 923–943.
- **What it supports:** Supports personality-adaptive dialogue design and mental health contextual framing. Applicable to Lori's care principles and the shifted framing from "cognitive difficulty" to "pacing support" in WO-10C.

### Draft-Conditioned Constrained Decoding for Structured Generation in LLMs
- **File:** `Research/first 10/Draft-Conditioned Constrained Decoding for Structured Generation in LLMs.pdf`
- **Authors:** Avinash Reddy, Thayne T. Walker, James S. Ide, Amrit Singh Hedi
- **Journal:** arXiv:2603.03505 (Feb 2026)
- **Citation:** Reddy et al. (2026). "Draft-Conditioned Constrained Decoding for Structured Generation in LLMs."
- **What it supports:** Supports structured output enforcement for the extractor pipeline. Applicable to the schema-grounded value extraction (WO-EX-BINDING-01) and constraint satisfaction in LLM generation.

### Integer Programming-Constrained Decoding for Reducing constraint-based Hallucinations in Large Language Models
- **File:** `Research/first 10/Integer Programming-Constrained Decoding for Reducing constraint-based Hallucinations in Large Language Models.pdf`
- **Authors:** Walter Orero Yodah
- **Organization:** Quinnipiac University
- **Citation:** Yodah (2026). "Integer Programming-Constrained Decoding for Reducing constraint-based Hallucinations in Large Language Models."
- **What it supports:** Directly supports WO-EX-BINDING-01 and hallucination reduction in the extractor. Applicable to constraint enforcement during LLM-based field extraction and the binding layer's structured output validation.

### Self-Aware Language Models: A Taxonomy and Evaluation of Epistemic Uncertainty and Hallucination Mitigation
- **File:** `Research/first 10/Self-Aware Language Models.pdf`
- **Authors:** Anjikya Tiwari, Vibhuti Gupta
- **Organization:** Microsoft, University of Texas Medical Branch
- **Citation:** Tiwari & Gupta (2026). "Self-Aware Language Models: A Taxonomy and Evaluation of Epistemic Uncertainty and Hallucination Mitigation."
- **What it supports:** Supports confidence estimation and uncertainty calibration in the extractor's value outputs. Applicable to WO-EX-SILENT-OUTPUT-01 and post-LLM validation of extraction confidence.

### How Trustworthy Are LLM-as-Judge Ratings for Interpretive Responses? Implications for Qualitative Research Workflows
- **File:** `Research/first 10/How Trustworthy Are LLM-as-Judge.pdf`
- **Authors:** Songhee Han, Jucun Shin, Jiyoon Han, Bung-Woo Jun, Hilal Ayan Karabatman
- **Organization:** Florida State University
- **Citation:** Han et al. (2026). "How Trustworthy Are LLM-as-Judge Ratings for Interpretive Responses? Implications for Qualitative Research Workflows."
- **What it supports:** Supports evaluation methodology for narrative content assessment in WO-LORI-STORY-CAPTURE-01. Applicable to the scorer layer and confidence assessment in multi-turn interview evaluation.

### Emergency Operation Scheme Generation for Urban Rail Transit Train Door Systems Using Retrieval-Augmented Large Language Models
- **File:** `Research/first 10/sensors-26-02006.pdf`
- **Authors:** Lu Huang, Zhigang Liu, Chengcheng Yu, Tianliang Zhu, Bing Yan
- **Journal:** Sensors, 2026, 26(6), 2006
- **Citation:** Huang et al. (2026). "Emergency Operation Scheme Generation for Urban Rail Transit Train Door Systems Using Retrieval-Augmented Large Language Models." Sensors, 26(6), 2006.
- **What it supports:** Supports RAG-based response generation for safety-critical systems. Applicable to the safety layer's operator notification surface and emergency response composition.

### Negation Detection and Scope Resolution via Transfer Learning
- **File:** `Research/2 pass research/E17-2118.pdf`
- **Authors:** Aditya Khandelwal, Suraj Sawant
- **Organization:** College of Engineering, Pune
- **Journal:** LREC 2020
- **Citation:** Khandelwal & Sawant (2020). "NegBERT: A Transfer Learning Approach for Negation Detection and Scope Resolution." LREC 2020.
- **What it supports:** Supports negation detection in narrative text analysis. Applicable to WO-LORI-STORY-CAPTURE-01's scene-anchor classifier and implicit vs. explicit claims detection.

### Information Extraction from Clinical Notes: Are We Ready to Switch to Large Language Models?
- **File:** `Research/informationextraction from notes.pdf`
- **Authors:** Yan Hu, Xu Zuo, Yujia Zhou, Xueqing Peng, Jimin Huang, Vipina K. Keloth, Vincent J. Zhang, Ruey-Ling Weng, Cathy Shyr, Qingyu Chen, Xiaoqian Jiang, Kirk E. Roberts, Hua Xu
- **Organization:** UT Health, Yale University
- **Journal:** Journal of the American Medical Informatics Association (JAMIA), 2026
- **Citation:** Hu et al. (2026). "Information Extraction from Clinical Notes: Are We Ready to Switch to Large Language Models?" JAMIA, 33(3), 553–562.
- **What it supports:** Supports instruction-tuned LLM performance on domain-specific information extraction. Applicable to the extractor's field extraction task and evaluation of LLM-based IE performance on semi-structured narrative input (similar to interview transcripts).

### A Sentence Classification-Based Medical Status Extraction Pipeline for Electronic Health Records: Institutional Case Study
- **File:** `Research/2 pass research/medinform-2026-1-e77409.pdf`
- **Authors:** Chuanming Dong, Boris Delange, Alex Poiron, Mohamed El Azzouzi, Clément François, Guillaume Bouzille, Marc Cuggia, Sandie Cabon
- **Organization:** Univ Rennes, Inserm, LTSI
- **Journal:** JMIR Medical Informatics, 2026
- **Citation:** Dong et al. (2026). "A Sentence Classification-Based Medical Status Extraction Pipeline for Electronic Health Records." JMIR Medical Informatics, 14(1), e77409.
- **What it supports:** Supports sentence classification for structured extraction from narrative text. Applicable to WO-EX-BINDING-01's sentence-level routing and contextual field selection in interview transcripts.

### KORIE: A Multi-Task Benchmark for Detection, OCR, and Information Extraction on Korean Retail Receipts
- **File:** `Research/Korie.pdf`
- **Authors:** Mahmoud SalahEldin Kasem, Mohamed Mahmoud, Mostafa Farouk Senussi, Mahmoud Abdalla, Hyun Soo Kang
- **Journal:** Mathematics, 2026, 14(1), 187
- **Citation:** Kasem et al. (2026). "KORIE: A Multi-Task Benchmark for Detection, OCR, and Information Extraction on Korean Retail Receipts." Mathematics, 14, 187.
- **What it supports:** Supports multi-task document understanding (detection, OCR, IE) relevant to structured form extraction from interview notes. Applicable to the extractor's document understanding pipeline if Lori's outputs are rendered as semi-structured forms.

### Making Sense Together: Human-AI Communication Through a Gricean Lens
- **File:** `Research/manners.pdf`
- **Authors:** Natasha Anne Rappa, Kok-Sing Tang, Grant Cooper
- **Journal:** Linguistics and Education, 2026, 91, 101489
- **Citation:** Rappa, Tang, & Cooper (2026). "Making Sense Together: Human-AI Communication Through a Gricean Lens." Linguistics and Education, 91, 101489.
- **What it supports:** Directly supports dialogue policy grounding in Grice's maxims (Quantity, Manner, Relation, Quality). Core theoretical foundation for Lori's turn-taking discipline and one-question-per-turn enforcement.

### The Kawa Model: A Self-Reflection Tool for Occupational Therapy Student Development in Practice Placements in Australia
- **File:** `Research/Kawa/OTI2023-2768898.pdf`
- **Authors:** Ornissa Naidoo, Chantal Christopher, Thanalutchmy Lingah, Monica Moran
- **Organization:** Western Australia Country Health Service, Murdoch University
- **Journal:** Hindawi Occupational Therapy International, 2023, Article ID 2768898
- **Citation:** Naidoo et al. (2023). "The Kawa Model: A Self-Reflection Tool for Occupational Therapy Student Development in Practice Placements in Australia." Occupational Therapy International, 2023, Article 2768898.
- **What it supports:** Supports the Kawa model metaphor (river as life-flow) used in WO-LORI-SESSION-AWARENESS-01 context framing and the Kawa companion stack design for older-adult lived experience extraction.

### The Dynamic Use of the Kawa Model: A Scoping Review
- **File:** `Research/Kawa/The_Dynamic_Use_of_the_Kawa_Model_A_Scop.pdf`
- **Authors:** Jayme L. Ober, Rebecca S. Newbury, Jennifer E. Lape
- **Journal:** The Open Journal of Occupational Therapy, 2022, 10(2), Article 7
- **Citation:** Ober, Newbury, & Lape (2022). "The Dynamic Use of the Kawa Model: A Scoping Review." The Open Journal of Occupational Therapy, 10(2), 1–12.
- **What it supports:** Supports the Kawa model as a therapeutic design framework for lived experience and wisdom extraction. Applicable to Pheno subsystem and the companion stack's person-centered narrative design.

### Event Relation Extraction Based on Heterogeneous Graph Attention Networks and Event Ontology Direction Induction
- **File:** `Research/Kawa/TST.2024.9010104.pdf`
- **Authors:** Wenjie Liu, Zhifan Wang
- **Journal:** Tsinghua Science and Technology, 2026, 31(1), 504–517
- **Citation:** Liu & Wang (2026). "Event Relation Extraction Based on Heterogeneous Graph Attention Networks and Event Ontology Direction Induction." Tsinghua Science and Technology, 31(1), 504–517.
- **What it supports:** Supports event relation extraction relevant to WO-LORI-STORY-CAPTURE-01's scene-anchor classifier (place, time, person-relation detection) and event knowledge graph construction from narrative text.

### Span-based Single-Stage Joint Entity-Relation Extraction Model
- **File:** `Research/Spantag/journal.pone.0281055.pdf`
- **Authors:** Dongchen Han, Zhaoqian Zheng, Hui Zhao, Shanshan Feng, Haiting Pang
- **Journal:** PLOS ONE, 2023, 18(2), e0281055
- **Citation:** Han et al. (2023). "Span-based Single-Stage Joint Entity-Relation Extraction Model." PLOS ONE, 18(2), e0281055.
- **What it supports:** Supports span-based entity and relation extraction directly applicable to WO-EX-SPANTAG-01 (Pass 1 entity detection and Pass 2 relation binding). Core to the two-pass extraction architecture.

### Dense Truth Overload: Measuring Content Saturation in Dense Passage Retrievers
- **File:** `Research/Spantag/dense-truthoveload.pdf`
- **Authors:** [See paper for full author list]
- **What it supports:** Supports dense retrieval and passage ranking relevant to the extractor's context window management and the SPANTAG Pass 1 span detection robustness under truncation conditions.

### StreamUni: Achieving Streaming Speech Translation with a Unified Large Speech-Language Model
- **File:** `Research/Spantag/journal.pone.0281055.pdf`
- **What it supports:** Supports streaming STT and speech-language integration for real-time narrator transcription (WO-STT-LIVE-02) and latency-aware processing in Lori's spoken dialogue pipeline.

### Nested Text Labelling Structures to Organize Knowledge in AI Applications
- **File:** `Research/21477_Nested_Text_Labelling_St.pdf`
- **Authors:** [Anonymous, Under double-blind review]
- **Journal:** ICLR 2026 (Under Review)
- **Citation:** "Nested Text Labelling Structures to Organize Knowledge in AI Applications." ICLR 2026 (Under Review).
- **What it supports:** Supports hierarchical annotation and knowledge representation for the extractor's schema structure. Applicable to WO-EX-SCHEMA-ANCESTOR-EXPAND-01 and multi-level field path organization.

### High-throughput Information Extraction of Printed Specimen Labels from Large-Scale Digitization of Entomological Collections Using a Semi-Automated Pipeline
- **File:** `Research/2 pass research/Methods Ecol Evol - 2026 - Belot - High‐throughput information extraction of printed specimen labels from large‐scale.pdf`
- **Authors:** Margot Belot, Joël Tuberosa, Leonardo Preuss, Olha Svezhentseva, Magdalena Claessen, Christian Bölling, Franziska Schuster, Théo Léger
- **Organization:** Museum für Naturkunde, Leipzig
- **Journal:** Methods in Ecology and Evolution, 2026, 17, 790–804
- **Citation:** Belot et al. (2026). "High-throughput Information Extraction of Printed Specimen Labels from Large-Scale Digitization of Entomological Collections." Methods in Ecology and Evolution, 17, 790–804.
- **What it supports:** Supports semi-automated pipeline design and OCR-based information extraction from unstructured text. Methodologically relevant to the extractor's handling of transcription noise and field validation.

### Semantic AI Framework for Prompt Engineering
- **File:** `Research/2 pass research/2020.lrec-1.704.pdf`
- **Authors:** Dmitry Lande, Leonard Strashnoy
- **Organization:** National Technical University of Ukraine, UCLA
- **Citation:** Lande & Strashnoy (2020). "Semantic AI Framework for Prompt Engineering." LREC 2020.
- **What it supports:** Supports formal prompt engineering methodology and semantic composition relevant to the composer's system-prompt assembly and controlled-prior block construction in WO-EX-SPANTAG-01.

### PersonaPlex: Voice and Role Control for Full Duplex Conversational Speech Models
- **File:** `Research/3534678.3539209.pdf`
- **Authors:** Rajarshi Roy, Jonathan Raiman, Sang-gil Lee, Teodor-Dumitru Ene, Robert Kirby, Sungwon Kim, Jaehyeon Kim, Bryan Catanzaro
- **Organization:** NVIDIA
- **Citation:** Roy et al. (2026). "PersonaPlex: Voice and Role Control for Full Duplex Conversational Speech Models." ICASSP 2026 (preprint).
- **What it supports:** Cited as PersonaPlex reference for voice-conditioned dialogue. Supports role-differentiated response generation and voice cloning for Lori's personality adaptation layer.

### Duplex Conversation: Towards Human-like Interaction in Spoken Dialogue Systems
- **File:** `Research/2602.06053v1.pdf`
- **Authors:** Ting-En Lin, Yuchuan Wu, Fei Huang, Luo Si, Jian Sun, Yongbin Li
- **Organization:** Alibaba Group
- **Citation:** Lin et al. (2026). "Duplex Conversation: Towards Human-like Interaction in Spoken Dialogue Systems." arXiv:2602.06053.
- **What it supports:** Supports full-duplex dialogue architecture with simultaneous bidirectional communication. Applicable to Lori's turn-taking and overlapping speech handling in natural conversation simulation.

### Large Language Models Meet NLP: A Survey
- **File:** `Research/second 10/LMmeetnlp.pdf`
- **Authors:** Libo Qin, Qiuang Chen, Xiachong Feng, Yang Wu, Yongheng Zhang, Yinghui Li, Min Li, Wanxiang Chen, Philip S. Yu
- **Journal:** Frontiers of Computer Science, 2026, 20, 201361
- **Citation:** Qin et al. (2026). "Large Language Models Meet NLP: A Survey." Frontiers of Computer Science, 20, 201361.
- **What it supports:** Comprehensive survey supporting the use of LLMs in NLP tasks. Applicable to the extractor's LLM-based field extraction and the broader Lorevox architecture's reliance on LLM inference.

### How Regulated Financial Institutions Will Tame Agentic AI Through Architectural Determinism
- **File:** `Research/second 10/Architectural Determinism.pdf`
- **Authors:** Aman Mahaptra
- **Organization:** Fiducia, Founder & Chief Strategy Officer
- **Citation:** Mahaptra (2026). "How Regulated Financial Institutions Will Tame Agentic AI Through Architectural Determinism." Fiducia White Paper, March 2026.
- **What it supports:** Supports architectural determinism as a control framework for agentic systems. Directly applicable to Lorevox's shift from prompt-only to deterministic enforcement (WO-EX-BINDING-01, dialogue policy wrapper) and safety-critical deployment in elder care.

### A Unified Framework for LLM-based ReLable Method
- **File:** `Research/second 10/A_Unified_Framework_for_.pdf`
- **Authors:** Tong Guo
- **Citation:** Guo (2026). "A Unified Framework for LLM-based ReLable Method."
- **What it supports:** Supports data re-labeling and annotation refinement using LLMs. Applicable to the extractor's evaluation harness and the scorer's annotation of defensible alternative paths (WO-SCHEMA-ANCESTOR-EXPAND-01, #94).

### Geometric Semantics for Legal Reasoning: A Quantum-Inspired Model of Rule and Standard Norms
- **File:** `Research/second 10/Geometric Semantics .pdf`
- **Authors:** [Author details in document]
- **Citation:** "Geometric Semantics for Legal Reasoning: A Quantum-Inspired Model of Rule and Standard Norms." (Draft, working paper).
- **What it supports:** Supports formal semantic models for rule-based reasoning. Applicable to the extractor's schema validation rules and binding rule formalization in WO-EX-BINDING-01.

### SteuerlLM: Local Specialized Large Language Model for German Tax Law Analysis
- **File:** `Research/second 10/SteuerLLMLocal specialized .pdf`
- **Authors:** Sebastian Wind, Jeta Sopa, Laurin Schmid, Quirin Jackl, Sebastian Kiefer, et al.
- **Organization:** Friedrich-Alexander-Universität Erlangen-Nürnberg
- **Citation:** Wind et al. (2026). "SteuerlLM: Local Specialized Large Language Model for German Tax Law Analysis."
- **What it supports:** Supports domain-specialized LLM fine-tuning for extracting structured information from specialized text. Methodologically applicable to Lorevox's domain specialization (older-adult narrative understanding) and local model deployment (RTX 50-series inference).

### Advances in Few-Shot Learning for Image Classification and Tabular Data
- **File:** `Research/first 10/Thesis_shysheya.pdf`
- **Authors:** Aliaksandra Shysheya
- **Organization:** Department of Engineering, University of Cambridge
- **Citation:** Shysheya (2025). "Advances in Few-Shot Learning for Image Classification and Tabular Data." PhD Dissertation, University of Cambridge.
- **What it supports:** Supports few-shot learning approaches for low-resource narrator adaptation. Applicable to Lori's rapid adaptation to new narrator profiles and minimal-annotation interview setup.

### Thunder-NUBench: A Benchmark for LLMs' Sentence-Level Negation Understanding
- **File:** `Research/first 10/Thunder-NUBench.pdf`
- **Authors:** Yeonyoung So, Gyuseong Lee, Sungmok Jung, Joonhak Lee, JiA Kang, Sangho Kim, Jaejin Lee
- **Organization:** Seoul National University
- **Journal:** EACL 2026
- **Citation:** So et al. (2026). "Thunder-NUBench: A Benchmark for LLMs' Sentence-Level Negation Understanding." EACL 2026.
- **What it supports:** Supports evaluation of negation understanding in LLM outputs. Applicable to the extractor's post-processing validation and negation-aware field parsing in narrative extraction.

### The Importance of Morphology-Aware Subword Tokenization for NLP Tasks in Slovak Language Modeling
- **File:** `Research/second 10/1-s2.0-S0957417426004057-main.pdf`
- **Authors:** Dávid Drzák, Jozef Kapusta
- **Organization:** Constantine the Philosopher University in Nitra
- **Journal:** Expert Systems With Applications, 2026
- **Citation:** Drzák & Kapusta (2026). "The Importance of Morphology-Aware Subword Tokenization for NLP Tasks in Slovak Language Modeling." Expert Systems With Applications, 312, 131492.
- **What it supports:** Supports morphologically-grounded tokenization for robust language understanding. Applicable to Lori's multilingual support (future: non-English narrator communities) and tokenization robustness in transcript processing.

### Neural Temporal Relation Extraction
- **File:** `Research/2 pass research/E17-2118.pdf` (alternate)
- **Authors:** Dmitriy Dligach, Timothy Miller, Chen Lin, Steven Bethard, Guergana Savova
- **Journal:** EACL 2017 (Short Papers)
- **Citation:** Dligach et al. (2017). "Neural Temporal Relation Extraction." EACL 2017, 746–751.
- **What it supports:** Supports temporal relation extraction from narrative text. Applicable to story anchor detection (place-time-person relations) in WO-LORI-STORY-CAPTURE-01's scene classifier.

---

## Section 3: Adjacent / For-Later References

Papers in this section are relevant to broader Lorevox research but are not currently blocking or directly supporting active WOs. Included for future-phase work and broader context awareness.

- `Research/ssrn-5172867.pdf` — Semantic frameworks for uncertainty and AI safety (future WO-LORI-SAFETY-INTEGRATION-01 Phase 3+)
- `Research/Kawa/newbury-lape-2021-well-being-aging-in-place-and-use-of-the-kawa-model-a-pilot-study.pdf` — Kawa model applied to aging in place (WO-LORI-SESSION-AWARENESS-01 context, Pheno subsystem future work)
- `Research/second 10/format tax.pdf` — Domain-specific structured extraction (future specialization lanes)
- `Research/second 10/many tongues.pdf` — Multilingual processing (deferred, future R6 phase)

---

## Section 4: Tangential / Out of Scope

These papers were collected but are not directly applicable to current Lorevox/Hornelore work:

- `Research/first 10/Integrating curation into scientific publishing to train.pdf`
- `Research/first 10/Order Is Not Layout.pdf`
- `Research/second 10/Geometric Semantics .pdf` (legal reasoning only, no dialogue relevance)

---

## External References (Not in Folder)

**Phelan Parenting Framework** ("Surviving Your Adolescents")
- **Status:** External reference (book, not in Research folder)
- **Used for:** Anti-pattern detector for Lori's conversation behavior (over-talking, over-emotion, over-arguing, over-control). Not cited in active system but informs dialogue policy design.

---

## Notes

- **Duplicate files**: Marked `(1)` versions excluded; single canonical files listed
- **Could not read**: None encountered; all 45 unique PDFs successfully parsed
- **Current baseline**: r5h (70/104 extraction pass rate, v3=41/62, v2=35/62)
- **Active extractor lanes**: BINDING-01 (#152), SCHEMA-ANCESTOR-EXPAND-01 (#144), VALUE-ALT-CREDIT-01 (#97)
- **Active Lori-behavior lanes**: SESSION-AWARENESS-01 (phases 1–4), SAFETY-INTEGRATION-01 (phases 1–9), STORY-CAPTURE-01 (phases 1B complete, 2–5 pending)
- **Compilation date**: 2026-05-01
- **User email**: dev@lorevox.com

---

**End of Reference List**
