from heapq         import heappop, heappush, heapify
from collections   import Counter
from random        import random, randbytes
from bitarray      import bitarray, decodetree
#from bitarray.util import huffman_code
from time          import time
from functools     import cache
from math          import log, floor, ceil
from bisect        import bisect_left, bisect_right


#############################################################

# Writing my own class instead of using bitarray's huffman_code()
# function as this implementation runs faster

class HuffmanCode:
  
  def __init__(self, probability_dict):
    """
    Takes a dictionary mapping symbols to their probabilities
      e.g. {'a': 0.25, 'b': 0.5, 'c': 0.25}
    """
    pairs = [(probability,random(),symbol) for (symbol,probability) in probability_dict.items()]
    heapify(pairs)
    while len(pairs) > 1:
      probability1, _, symbol1 = heappop(pairs)
      probability2, _, symbol2 = heappop(pairs)
      new_pair = (probability1 + probability2, random(), {0:symbol1, 1:symbol2})
      heappush(pairs, new_pair)
    self.tree = pairs[0][2]
    self.symbol_encoding = HuffmanCode._reverse_lookup(self.tree)
   
  @staticmethod
  def _reverse_lookup(tree, prefix=None):
    if prefix is None: prefix = bitarray()
    reverse_lookup_table = {}
    for branch in [0,1]:
      if branch in tree:
        if type(tree[branch])==dict:
          reverse_lookup_table |= HuffmanCode._reverse_lookup(tree[branch],prefix+[branch])
        else:
          reverse_lookup_table |= {tree[branch]: prefix+[branch]}
    return reverse_lookup_table
  
  def encode(self, symbol):
    return self.symbol_encoding[symbol]
  
  def decode(self, bitarr, index):
    entry = self.tree
    while type(entry) == dict and index<len(bitarr):
      entry = entry[bitarr[index]]
      index += 1
    return (None if type(entry)==dict else entry), index


#############################################################

class ArithmeticCode:
  
  def __init__(self, probability_dict):
    total = sum(probability_dict.values())
    intervals = [(frequency/total,symbol) for (symbol,frequency) in probability_dict.items()]
    intervals.sort(reverse=True)
    steps = [(0., 256)]
    for probability, symbol in intervals:
      prev_probability, prev_symbol = steps[-1]
      steps.append((prev_probability + probability, symbol))
    self.steps = steps
    self.intervals = {steps[i][1]: (steps[i-1][0],steps[i][0]) for i in range(1,len(steps))}
    
  def encode(self, symbol):
    interval_start, interval_end = self.intervals[symbol]
    interval_size = interval_end - interval_start
    scale = 2**floor(-log(interval_size, 2))
    while ceil(interval_end*scale) - ceil(interval_start*scale) < 2:
      scale *= 2
    return bitarray(bin(ceil(interval_start*scale + scale))[3:])
    
  def decode(self, bitarr, index):
    integer_representation = 0
    scale = 1
    start_index, end_index = 0, 1
    while start_index != end_index and index < len(bitarr):
      integer_representation *= 2
      integer_representation += bitarr[index]
      index += 1
      scale *= 2
      interval_start = (integer_representation / scale, 1e400)
      interval_end   = ((integer_representation + 1) / scale, -1e400)
      start_index = bisect_right(self.steps, interval_start)
      end_index   = bisect_left (self.steps, interval_end)
    if start_index != end_index: return (None, index)
    return (self.steps[end_index][1], index)



#############################################################


class Predictor:
  
  def __init__(self, text, window = 6, Code = ArithmeticCode):
    self.window = window
    self.Code = Code
    self.cached_huffman_codes = {}
    self.train(text)
  
  def train(self, text):
    
    self.completions = {}
    
    for i in range(len(text)-self.window+1):
      stub = text[i:i+self.window-1]
      if stub in self.completions:
        self.completions[stub].update([text[i+self.window-1]])
      else: self.completions[stub] = Counter([text[i+self.window-1]])
    
    for stub in self.completions:
      for completion in self.completions[stub]:
        self.completions[stub][completion] *= 1000000
      self.completions[stub].update(bytes(range(256)))
    
    self.byte_counts = Counter(text)
    self.byte_counts.update(bytes(range(256)))
    
    self.default_huffman_code = self.Code(self.byte_counts)
  
  def huffman_for_stub(self, stub):
    if stub in self.cached_huffman_codes:
      huffman_code = self.cached_huffman_codes[stub]
    elif stub in self.completions:
      huffman_code = self.Code(self.completions[stub])
      self.cached_huffman_codes[stub] = huffman_code
    else:
      huffman_code = self.default_huffman_code
    return huffman_code
  
  def encode(self, text):
    out = bitarray()
    for i in range(len(text)):
      stub = text[i-self.window+1:i]
      huffman_code = self.huffman_for_stub(stub)
      out.extend(huffman_code.encode(text[i]))
    return out.tobytes() + (len(out)%8).to_bytes()
    
  def decode(self, encoded_text, prefix=None):
    encoded_text_len_mod_8 = encoded_text[-1]
    encoded_bits = bitarray()
    encoded_bits.frombytes(encoded_text)
    encoded_bits = encoded_bits[:-8-(8-encoded_text_len_mod_8)%8]
    out = list(prefix) if prefix else []
    index = 0
    while index < len(encoded_bits):
      stub = bytes(out[len(out)-self.window+1:len(out)]) if len(out)>=self.window-1 else b''
      huffman_code = self.huffman_for_stub(stub)
      symbol, new_index = huffman_code.decode(encoded_bits, index)
      if symbol is None: break
      out.append(symbol)
      index = new_index
    return bytes(out)
  
  def encoding_probabilities_ranks(self, text):
    symbols       = []
    probabilities = []
    ranks         = []
    for i in range(len(text)):
      stub   = text[i-self.window+1:i]
      symbol = text[i]
      symbol_expectations = self.completions[stub] if stub in self.completions else self.byte_counts
      symbol_frequency   = symbol_expectations[symbol]
      symbol_probability = symbol_expectations[symbol]/symbol_expectations.total()
      symbol_rank = len([sym for sym,freq in symbol_expectations.items() if freq>symbol_frequency])+1
      
      symbols.append(symbol)
      probabilities.append(symbol_probability)
      ranks.append(symbol_rank)
    return (symbols, probabilities, ranks)


#############################################################


if __name__ == "__main__":

    war_and_peace = open('../../../Data/books/pg2600.txt','rb+').read()

    war_and_peace_predictor = Predictor(war_and_peace, window=6, Code=ArithmeticCode)

    inigo_text     = b'Hello. My name is Inigo Montoya. You killed my father. Prepare to die.'
    inigo_encoding = war_and_peace_predictor.encode(inigo_text)
    inigo_decoding = war_and_peace_predictor.decode(inigo_encoding)

    print(len(inigo_encoding), inigo_encoding.hex())
    print(len(inigo_decoding), inigo_decoding)


    #############################################################


    print('\nThe predictor trained on War and Peace generates the ' +\
          'following example completion for the word "Nicholas":')
          
    print(war_and_peace_predictor.decode(randbytes(50)+b'\0', prefix=b'Nicholas').decode('utf8').__repr__())


    #############################################################

    # Use the predictor trained on War and Peace to compress
    #   various texts
    
    chosen_books = {
        "pg10.txt": "The King James Version of the Bible",
        "pg100.txt": "The Complete Works of William Shakespeare",
        "pg11.txt": "Alice's Adventures in Wonderland",
        "pg1184.txt": "The Count of Monte Cristo",
        "pg145.txt": "Middlemarch",
        "pg996.txt": "Don Quixote",
        "pg2554.txt": "Crime and Punishment",
        "pg2600.txt": "War and Peace",
    }
    
    text_fnames = list(chosen_books.keys())
    book_titles = list(chosen_books.values())
    compression_ratios = []
    
    huffman_predictor    = Predictor(war_and_peace, window=6, Code=HuffmanCode)
    arithmetic_predictor = war_and_peace_predictor
    
    for text_fname in text_fnames:
      current_text = open('../../../Data/books/'+text_fname,'rb+').read()
      
      huffman_compressed_text    = huffman_predictor.encode(current_text)
      huffman_compression_ratio  = len(current_text) / len(huffman_compressed_text)
      
      arithmetic_compressed_text = arithmetic_predictor.encode(current_text)
      arithmetic_compression_ratio  = len(current_text) / len(arithmetic_compressed_text)
      
      compression_ratios.append([huffman_compression_ratio, arithmetic_compression_ratio])
      
    import pandas as pd
    
    columns = ['Huffman compression size', 'Arithmetic compression size']
    WP_performance = pd.DataFrame(columns = columns, index = book_titles, data = compression_ratios)
    
    print(WP_performance)