from typing import List, Dict
import re

# Split text into chunks with page number preservation.
def chunk_text(pages_data: List[Dict[str, any]], chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, any]]:

    chunks = []
    
    for page_data in pages_data:
        page_num = page_data['page_number']
        text = page_data['text']
        
        page_chunks = _split_into_chunks(text, chunk_size, overlap)
        
        for idx, chunk_text in enumerate(page_chunks):
            chunks.append({
                'page_number': page_num,
                'chunk_text': chunk_text,
                'chunk_index': idx
            })
    
    return chunks


# Split text into chunks of approximately chunk_size tokens.
def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:

    words = text.split()
    chunks = []
    
    if not words:
        return []
    
    current_chunk = []
    current_size = 0
    
    for word in words:
        word_size = len(word.split())
        if current_size + word_size > chunk_size and current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append(chunk_text)
            
            overlap_words = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_words + [word]
            current_size = len(overlap_words) + word_size
        else:
            current_chunk.append(word)
            current_size += word_size
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

# Split text by paragraphs, respecting min/max chunk sizes.
def chunk_by_paragraphs(pages_data: List[Dict[str, any]], min_chunk_size: int = 200, max_chunk_size: int = 1000) -> List[Dict[str, any]]:
    
    chunks = []
    
    for page_data in pages_data:
        page_num = page_data['page_number']
        text = page_data['text']
        
        paragraphs = re.split(r'\n\s*\n', text)
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_size = len(para.split())
            
            if current_size + para_size > max_chunk_size and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)
                if len(chunk_text.split()) >= min_chunk_size:
                    chunks.append({
                        'page_number': page_num,
                        'chunk_text': chunk_text,
                        'chunk_index': len([c for c in chunks if c['page_number'] == page_num])
                    })
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if len(chunk_text.split()) >= min_chunk_size:
                chunks.append({
                    'page_number': page_num,
                    'chunk_text': chunk_text,
                    'chunk_index': len([c for c in chunks if c['page_number'] == page_num])
                })
    
    return chunks
