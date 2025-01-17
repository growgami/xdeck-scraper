"""Category mappings and configurations for the news bot"""

from typing import Dict, List

# Mapping of column IDs to category names
CATEGORY_MAP: Dict[str, str] = {
    '0': 'NEAR Ecosystem',
    '1': 'Polkadot Ecosystem',
    '2': 'Arbitrum Ecosystem',
    '3': 'IOTA Ecosystem',
    '4': 'AI Agents',
    '5': 'DefAI'
}

# Mapping of category names to Telegram channel keys
TELEGRAM_CHANNEL_MAP: Dict[str, str] = {
    'NEAR Ecosystem': 'near',
    'Polkadot Ecosystem': 'polkadot',
    'Arbitrum Ecosystem': 'arbitrum',
    'IOTA Ecosystem': 'iota',
    'AI Agents': 'ai_agent',
    'DefAI': 'defai'
}

# Category-specific focus areas for news filtering
CATEGORY_FOCUS: Dict[str, List[str]] = {
    'NEAR Ecosystem': [
        'Protocol Development & Infrastructure',
        'DeFi and Smart Contract Innovations',
        'Cross-chain Integrations & Bridges',
        'Developer Tools & SDKs',
        'Ecosystem Growth & Adoption',
        'AI & Web3 Integration'
    ],
    'Polkadot Ecosystem': [
        'Parachain Development & Integration',
        'Cross-chain Messaging (XCM)',
        'Governance & Treasury',
        'Technical Infrastructure',
        'Ecosystem Partnerships'
    ],
    'Arbitrum Ecosystem': [
        'Layer 2 Scaling Solutions',
        'Protocol Deployments & TVL',
        'Governance & DAO Activities',
        'Infrastructure Development',
        'Ecosystem Growth Initiatives'
    ],
    'IOTA Ecosystem': [
        'Protocol Development & Updates',
        'Smart Contract Platform',
        'IoT Integration & Use Cases',
        'Network Security & Performance',
        'Industry Partnerships'
    ],
    'AI Agents': [
        'Agent Development Frameworks',
        'AI-Blockchain Integration',
        'Autonomous Systems & DAOs',
        'Multi-agent Systems',
        'AI Safety & Governance',
        'Real-world Applications'
    ],
    'DefAI': [
        'Decentralized AI Infrastructure',
        'AI Model Training & Deployment',
        'Data Privacy & Security',
        'Tokenized AI Systems',
        'Cross-chain AI Solutions'
    ]
}

# Emoji mappings for subcategories
EMOJI_MAP: Dict[str, str] = {
    # Technical & Development
    'Protocol Development': '⚡',
    'Technical Infrastructure': '🔧',
    'Infrastructure Development': '🔧',
    'Network Security': '🔒',
    'Developer Tools': '🛠️',
    
    # Integration & Partnerships
    'Cross-chain Integration': '🌉',
    'Industry Partnerships': '🤝',
    'Ecosystem Partnerships': '🤝',
    'IoT Integration': '📱',
    
    # Governance & Community
    'Governance': '⚖️',
    'Treasury': '💰',
    'DAO Activities': '🏛️',
    
    # Growth & Adoption
    'Ecosystem Growth': '📈',
    'Adoption': '🚀',
    'TVL': '💹',
    
    # AI & Innovation
    'AI Integration': '🤖',
    'AI Development': '🧠',
    'AI Safety': '🛡️',
    'Multi-agent Systems': '🎯',
    
    # Default
    'Other Updates': '📌'
} 