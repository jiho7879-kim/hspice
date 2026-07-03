---
title: 'HSPICE Output Parsing Guide for Python Automation'
subtitle: 'Parsing .mt0, .st0, .lis, and Binary POST (.tr0/.sw0/.ac0) Files'
version: '1.0'
date: '2026-06-30'
description: 'Complete guide for programmatic parsing of HSPICE output files in Python. Covers .mt0/.st0 measurement tables, .lis listing files, and binary Post-Processing (.tr0/.sw0/.ac0) waveform files.'
tags: [HSPICE, output, parsing, Python, automation, RAG, mt0, st0, tr0, lis]
language: 'Python'
keywords: [parsing, mt0, st0, tr0, lis, measurement, waveform, HSPICE output, Python, regex]
---

# HSPICE Output Parsing Guide for Python Automation

> **Purpose**: Complete reference for programmatically extracting simulation results from HSPICE output files.
> **Scope**: .mt0/.st0 (measurement tables), .lis (listing/log), binary POST format (.tr0/.sw0/.ac0).
> **Target**: Python-based RAG system for SRAM/UT characterization automation.

---

## Table of Contents

1. [Output File Types Overview](#1-output-file-types-overview)
2. [Parsing .mt0 / .st0 Measurement Files](#2-parsing-mt0--st0-measurement-files)
3. [Parsing .lis Listing Files](#3-parsing-lis-listing-files)
4. [Parsing Binary POST Files (.tr0/.sw0/.ac0)](#4-parsing-binary-post-files-tr0sw0ac0)
5. [HSPICE Output Control Options](#5-hspice-output-control-options)
6. [Python Workbench Automation](#6-python-workbench-automation)
7. [Complete Python Parsing Library](#7-complete-python-parsing-library)
8. [Integration with RAG System](#8-integration-with-rag-system)
9. [References](#9-references)

---

## 1. Output File Types Overview

### 1.1 File Extension Summary
| Extension | Content | Format | When Generated |
|-----------|---------|--------|----------------|
| .mt0 | DC/AC measurement results | ASCII table | .DC or .AC with .MEASURE |
| .st0 | Transient measurement results | ASCII table | .TRAN with .MEASURE |
| .mt# | Monte Carlo per-run measurements | ASCII table | Each MC run result |
| .mc0 | Monte Carlo statistical summary | ASCII text | After .MC completes |
| .lis | Listing file (log + results) | ASCII text | Every simulation |
| .tr0 | Transient waveforms | Binary POST | .TRAN with POST=2 |
| .sw0 | DC sweep waveforms | Binary POST | .DC with POST=2 |
| .ac0 | AC analysis waveforms | Binary POST | .AC with POST=2 |
| .gr# | Optimizer result data | ASCII data | .OPTIMIZE with OUTPUT=DATA |

### 1.2 Controlling Output with .OPTION
.OPTIONS POST=2       * Enable binary waveform output (.tr0/.sw0)
.OPTIONS PROBE=1      * Only save nodes listed in .PROBE
.OPTIONS MEASOUT=1    * Output .mt0/.st0 measurement files
.OPTIONS LISFILE=1    * Write detailed .lis listing file
.OPTIONS INGOLD=2     * Use newer numerical format (avoids scientific notation issues)

### 1.3 Output File Naming Convention
`
[deck_name].[analysis_type][run_number]
  sram_char.dc.mt0        * DC measurement, run 0
  sram_char.tran.mt0      * TRAN measurement, run 0
  sram_char.tran.st0      * TRAN measurement (same as mt0 for TRAN)
  sram_char.mc0           * Monte Carlo summary
  sram_char.tr0           * Transient waveform (POST binary)
  sram_char.sw0           * DC sweep waveform (POST binary)
`

---

## 2. Parsing .mt0 / .st0 Measurement Files

### 2.1 File Format Structure
.mt0/.st0 files are ASCII text with a standardized format:

Header lines:
`
 SOURCE='HSPICE' VERSION='2021.09-SP1'
 'SRAM 6T Characterization'
 'Jun 30 12:00:00 2026'
 'DC'
`

Column headers (tab-delimited):
`
INDEX    RSNM        IREAD       WNM        VTRIP
`

Data rows (tab-delimited):
`
0        1.852e-01   3.210e-05   2.450e-01   4.120e-01
`

### 2.2 Python Parser for .mt0 Files
`python
import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

def parse_mt0(filepath: str) -> pd.DataFrame:
    '''
    Parse HSPICE .mt0/.st0 measurement output file.

    Args:
        filepath: Path to .mt0 or .st0 file

    Returns:
        DataFrame with column names matching HSPICE .MEASURE names.
        Each row is one simulation run or .ALTER case.

    Raises:
        FileNotFoundError: File does not exist
        ValueError: File format not recognized
    '''
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f'File not found: {filepath}')

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Find column header line (starts with INDEX or tab-separated header)
    header_line_idx = None
    data_start_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip comments and empty lines
        if stripped.startswith('$') or not stripped:
            continue
        # Detect header: first non-comment line with INDEX or measurement names
        if '\tINDEX' in line or line.startswith('INDEX'):
            header_line_idx = i
            data_start_idx = i + 1
            break

    if header_line_idx is None:
        # Try alternative format: space-delimited header
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('$') or not stripped:
                continue
            # Check if line looks like a header (all words are valid identifiers)
            words = stripped.split()
            if words and words[0] == 'INDEX':
                header_line_idx = i
                data_start_idx = i + 1
                break

    if header_line_idx is None:
        raise ValueError(f'Could not find header line in {filepath}')

    # Parse column names
    header_line = lines[header_line_idx].strip()
    # Handle both tab and space delimiters
    if '\t' in header_line:
        columns = [col.strip() for col in header_line.split('\t')]
    else:
        columns = header_line.split()
        columns = [col for col in columns if col]  # Remove empty strings

    # Parse data rows
    data = []
    for i in range(data_start_idx, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith('$'):
            continue

        # Split by tab or space
        if '\t' in line:
            values = line.split('\t')
        else:
            values = line.split()
            values = [v for v in values if v]

        if len(values) != len(columns):
            # Try to handle continuation lines or malformed rows
            continue

        # Convert to float (INDEX is int)
        row = {}
        for col, val in zip(columns, values):
            try:
                row[col] = float(val) if '.' in val else int(val)
            except ValueError:
                row[col] = val  # Keep as string if conversion fails
        data.append(row)

    return pd.DataFrame(data)
`

### 2.3 Usage Example
`python
# Parse single .mt0 file
df = parse_mt0('sram_char.dc.mt0')
print(df.columns.tolist())
# ['INDEX', 'RSNM', 'IREAD', 'WNM', 'VTRIP']

print(f'RSNM mean: {df[\"RSNM\"].mean():.3f} V')
print(f'RSNM sigma: {df[\"RSNM\"].std():.3f} V')
`

### 2.4 Parsing Monte Carlo .mt# Files
`python
from pathlib import Path
import re

def parse_mc_runs(directory: str, base_pattern: str = 'sram_char.dc.mt') -> pd.DataFrame:
    '''
    Parse Monte Carlo per-run measurement files (.mt#, # = run number).

    Args:
        directory: Directory containing .mt# files
        base_pattern: Base filename pattern (e.g., 'sram_char.dc.mt')

    Returns:
        DataFrame: One row per MC run, columns = measurement names
    '''
    path = Path(directory)
    mt_files = sorted(path.glob(f'{base_pattern}*'),
                      key=lambda f: int(re.search(r'\d+$', f.stem).group()))

    all_runs = []
    for f in mt_files:
        df_run = parse_mt0(str(f))
        all_runs.append(df_run.iloc[0].to_dict())

    return pd.DataFrame(all_runs)

# Usage
mc_df = parse_mc_runs('./', 'sram_char.dc.mt')
print(f'MC runs: {len(mc_df)}')
print(f'RSNM: mu={mc_df[\"RSNM\"].mean():.4f}, sigma={mc_df[\"RSNM\"].std():.4f}')
`

---

## 3. Parsing .lis Listing Files

### 3.1 What .lis Contains
The .lis file contains:
- Netlist expansion (component summary)
- Operating point information (node voltages, currents)
- .MEASURE results (same as .mt0)
- Optimization iteration history
- Error and warning messages
- CPU time and memory statistics

### 3.2 Key Sections in .lis
`
 ****** HSPICE Summary (complete listing) ******

 ** Device Model Summary **
 .MODEL NMOS_SRAM NMOS LEVEL=14
 .MODEL PMOS_SRAM PMOS LEVEL=14

 ** Operating Point Information **
 node   = voltage
 VVDD   = 7.8208e-01
 VVDD2  = 1.7921e-02

 ** DC Transfer Characteristics **
 VVDD_SRC          V(VVDD)          V(VVDD2)
 0.000E+00        0.000E+00        0.000E+00
 1.000E-02        9.998E-03        3.210E-03

 ** Measure Results **
 rsnm                    = 1.852e-01
 iread                   = 3.210e-05
 wnm                     = 2.450e-01

 ** transient time **         0.12 seconds
 ** total memory **           8.40M
 ** cpu time **               0.25 seconds
`

### 3.3 Python Parser for .lis
`python
import re
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

class LisParser:
    '''Parse HSPICE .lis listing file for key simulation results.'''

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.content = self.filepath.read_text()
        self.measurements: Dict[str, float] = {}
        self.cpu_time: Optional[float] = None
        self.corner: Optional[str] = None
        self.parse()

    def parse(self):
        '''Parse measurement results from .lis file.'''
        # Extract .MEASURE results
        # Format: 'measure_name = value'
        measure_pattern = re.compile(
            r'^\s+(\w+)\s+=\s+([+-]?\d+\.?\d*[eE]?[+-]?\d*)',
            re.MULTILINE
        )
        for match in measure_pattern.finditer(self.content):
            name, value = match.group(1), match.group(2)
            try:
                self.measurements[name.lower()] = float(value)
            except ValueError:
                pass

        # Extract CPU time
        cpu_match = re.search(r'\*\* cpu time\s+\*\*\s+([\d.]+)\s+seconds', self.content)
        if cpu_match:
            self.cpu_time = float(cpu_match.group(1))

    def get_measurement(self, name: str) -> Optional[float]:
        '''Get a specific measurement value (case-insensitive).'''
        return self.measurements.get(name.lower())

    def get_all_measurements(self) -> Dict[str, float]:
        '''Get all parsed measurements.'''
        return dict(self.measurements)

    def to_dataframe(self) -> pd.DataFrame:
        '''Convert measurements to a single-row DataFrame.'''
        return pd.DataFrame([self.measurements])


def parse_lis_batch(lis_files: list) -> pd.DataFrame:
    '''Parse multiple .lis files into a combined DataFrame.'''
    records = []
    for f in lis_files:
        parser = LisParser(f)
        records.append(parser.get_all_measurements())
    return pd.DataFrame(records)


# Usage
parser = LisParser('sram_char.lis')
print(parser.get_measurement('rsnm'))  # 0.1852
print(f'CPU time: {parser.cpu_time}s')

# Batch parse all .lis in directory
from pathlib import Path
lis_files = list(Path('.').glob('*.lis'))
df = parse_lis_batch(lis_files)
`

### 3.4 Extracting Operating Point
`python
def parse_operating_point(lis_content: str) -> Dict[str, float]:
    '''Extract DC operating point node voltages from .lis.'''
    op_section = re.search(
        r'\*\* Operating Point Information \*\*(.*?)(?=\*\*|\Z)',
        lis_content, re.DOTALL
    )
    if not op_section:
        return {}

    op_lines = op_section.group(1).strip().split('\n')
    op_data = {}
    for line in op_lines:
        # Format: 'node_name   =   voltage'
        match = re.match(r'\s*(\S+)\s+=\s+([+-]?\d+\.?\d*[eE]?[+-]?\d*)', line)
        if match:
            op_data[match.group(1)] = float(match.group(2))
    return op_data
`

### 3.5 Extracting Error/Warning Messages
`python
def parse_errors_from_lis(filepath: str) -> list:
    '''Extract all error and warning messages from .lis file.'''
    content = Path(filepath).read_text()
    errors = []

    # HSPICE error patterns
    error_patterns = [
        r'\*\*\* ERROR \*\*\* :?(.+?)(?=\n\s*\*|\Z)',
        r'\*\*\* WARNING \*\*\* :?(.+?)(?=\n\s*\*|\Z)',
        r'**warning\*\* :?(.+?)(?=\n|\Z)',
    ]

    for pattern in error_patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        errors.extend([m.strip() for m in matches])

    return errors
`

---

## 4. Parsing Binary POST Files (.tr0/.sw0/.ac0)

### 4.1 POST Binary Format Overview
HSPICE POST binary files (.tr0, .sw0, .ac0) use a proprietary format:
- 512-byte header with metadata
- Signal index table (node names, types)
- Binary data blocks per time/sweep point
- Each signal can be: voltage, current, power, or complex

### 4.2 Parsing with PyHSPICE (Recommended)
The pyhspice library provides direct POST file access:
`python
# Install: pip install pyhspice
from pyhspice import post_parser

def parse_tr0_with_pyhspice(filepath: str, signals: list = None):
    '''
    Parse .tr0/.sw0 POST binary file using pyhspice.

    Args:
        filepath: Path to .tr0 or .sw0 file
        signals: List of signal names to extract (None = all)

    Returns:
        dict: {signal_name: numpy_array_of_values}
        time_axis: numpy array of time/sweep points
    '''
    result = post_parser.parse(filepath)

    time_axis = result.get_time_axis()
    signal_data = {}

    for signal in result.get_all_signals():
        name = signal.get_name()
        if signals is None or name in signals:
            signal_data[name] = signal.get_values()

    return {
        'time': time_axis,
        'signals': signal_data,
        'metadata': result.get_metadata()
    }

# Usage
data = parse_tr0_with_pyhspice('sram_char.tr0',
                                 signals=['V(VVDD)', 'V(VVDD2)', 'V(BL)'])

import matplotlib.pyplot as plt
plt.plot(data['time'], data['signals']['V(VVDD)'])
plt.plot(data['time'], data['signals']['V(VVDD2)'])
plt.xlabel('Time (s)')
plt.ylabel('Voltage (V)')
`

### 4.3 Fallback: Raw Binary Parsing (without pyhspice)
If pyhspice is unavailable, parse the raw POST binary format:
`python
import struct
import numpy as np

def parse_post_binary_raw(filepath: str):
    '''
    Basic raw binary POST parser (limited capability).
    Reads header and identifies signal names and data blocks.
    '''
    with open(filepath, 'rb') as f:
        # Read 512-byte header
        header = f.read(512)

        # Extract signal count from header offset
        num_signals = struct.unpack_from('<i', header, 16)[0]

        # Read signal name table
        signal_names = []
        for i in range(num_signals):
            name_start = 64 + i * 32
            name_bytes = header[name_start:name_start + 32]
            name = name_bytes.split(b'\\x00')[0].decode('ascii', errors='replace')
            signal_names.append(name.strip())

        # Parse data blocks
        data_blocks = {name: [] for name in signal_names}
        time_points = []

        while True:
            # Each data block: time_value + n_signal_values
            block_header = f.read(8)
            if len(block_header) < 8:
                break

            time_val = struct.unpack('<d', block_header)[0]
            time_points.append(time_val)

            for name in signal_names:
                val_bytes = f.read(8)
                if len(val_bytes) < 8:
                    break
                val = struct.unpack('<d', val_bytes)[0]
                data_blocks[name].append(val)

    return {
        'time': np.array(time_points),
        'signals': {name: np.array(vals) for name, vals in data_blocks.items()}
    }
`

### 4.4 Converting POST to CSV (for RAG ingestion)
`python
def post_to_csv(tr0_file: str, csv_file: str, signals: list = None):
    '''Convert POST binary to CSV for RAG ingestion.'''
    data = parse_tr0_with_pyhspice(tr0_file)

    df = pd.DataFrame({'time_s': data['time']})
    for name, values in data['signals'].items():
        if signals is None or name in signals:
            col_name = name.replace('(', '_').replace(')', '_').replace(',', '_')
            df[col_name] = values

    df.to_csv(csv_file, index=False)
    print(f'Saved {len(df)} samples to {csv_file}')
    return df
`

---

## 5. HSPICE Output Control Options

### 5.1 Critical .OPTIONS for Output
| Option | Values | Effect |
|--------|--------|--------|
| POST | 0/1/2/3 | 0=no output, 1=text, 2=binary, 3=compressed |
| PROBE | 0/1 | 0=save all, 1=save only .PROBE nodes |
| MEASOUT | 0/1 | 0=no .mt0, 1=write .mt0/.st0 |
| LISFILE | 0/1/2 | 0=no .lis, 1=brief, 2=verbose |
| INGOLD | 1/2 | 1=short format, 2=long format numbers |
| NODE | YES/NO | Print node names in output |
| CAPTAB | YES/NO | Print capacitance table |
| WIDTH | <n> | Output line width in .lis |

### 5.2 .MEASURE Output Options
.MEASURE DC RSNM MIN V(VVDD,VVDD2)
.MEASURE DC RSNM_FILE MIN V(VVDD,VVDD2) FILE='rsnm_meas.txt'
* Write this measure to a separate file

.MEASURE DC RSNM_MT0 MIN V(VVDD,VVDD2) MEASOUT=1
* Force this measure into .mt0 even if MEASOUT=0

### 5.3 Saving Post-Processed Data (.PRINT)
.PRINT DC V(VVDD) V(VVDD2) I(VDD_SRC)
* ASCII tabular output in .lis

.PRINT V(VVDD) V(VVDD2) WIDTH=80
* Control output column width for readability

.PROBE DC V(VVDD) V(VVDD2) I(MPG1)
* Limit binary output to specific signals (reduces file size)

### 5.4 Output File Size Considerations
| File Type | Size Scaling | Concern |
|-----------|-------------|---------|
| .lis | ~10 KB per 100 DC points | OK for small runs |
| .tr0 (all nodes) | 1-100 MB | Large for 100K+ time points |
| .tr0 (PROBE only) | 10-50% of full | Recommended for most runs |
| .mt0 | ~1 KB per run | Trivial |
| .mc0 | ~1 KB | Trivial |

---

## 6. Python Workbench Automation

### 6.1 Running HSPICE and Collecting Results
`python
import subprocess
import pandas as pd
from pathlib import Path
from typing import Optional

class HspiceWorkbench:
    '''Automate HSPICE simulation runs and result collection.'''

    def __init__(self, hspice_path: str = 'hspice'):
        self.hspice_path = hspice_path
        self.results = []

    def run_netlist(self, netlist: str, work_dir: str = '.') -> dict:
        '''
        Run HSPICE on a netlist file and collect results.

        Args:
            netlist: Path to .sp netlist file
            work_dir: Working directory for simulation

        Returns:
            dict with keys: deck_name, mt0_df, lis_parser, success, cpu_time
        '''
        netlist_path = Path(netlist)
        deck_name = netlist_path.stem
        
        # Run HSPICE
        cmd = [self.hspice_path, '-i', str(netlist_path), '-o', deck_name]
        result = subprocess.run(
            cmd, cwd=work_dir, capture_output=True, text=True
        )

        success = result.returncode == 0

        # Collect results
        output = {'deck_name': deck_name, 'success': success}

        # Parse .mt0 if exists
        mt0_file = Path(work_dir) / f'{deck_name}.mt0'
        if mt0_file.exists():
            output['mt0_df'] = parse_mt0(str(mt0_file))

        # Parse .lis if exists
        lis_file = Path(work_dir) / f'{deck_name}.lis'
        if lis_file.exists():
            output['lis_parser'] = LisParser(str(lis_file))
            output['cpu_time'] = output['lis_parser'].cpu_time

        return output

    def run_sweep(self, netlist_template: str, params: list) -> pd.DataFrame:
        '''
        Run parameterized sweep by substituting values into netlist template.

        Args:
            netlist_template: Netlist file path with {PARAM} placeholders
            params: List of dicts with parameter values

        Returns:
            DataFrame: Sweep results aggregated
        '''
        template = Path(netlist_template).read_text()
        all_results = []

        for i, param_set in enumerate(params):
            # Create deck with substituted parameters
            content = template.format(**param_set)
            deck_name = f'sweep_{i:03d}'
            deck_file = Path(f'{deck_name}.sp')
            deck_file.write_text(content)

            # Run
            result = self.run_netlist(str(deck_file))
            if result.get('mt0_df') is not None:
                row = param_set.copy()
                row.update(result['mt0_df'].iloc[0].to_dict())
                all_results.append(row)

            # Cleanup
            deck_file.unlink()

        return pd.DataFrame(all_results)


# Usage
wb = HspiceWorkbench(hspice_path='C:/synopsys/hspice/bin/hspice.exe')
result = wb.run_netlist('sram_char.sp')
if result['success']:
    print(f'CPU time: {result[\"cpu_time\"]}s')
    print(result['mt0_df'])
`

### 6.2 Batch Monte Carlo Post-Processing
`python
def analyze_mc_results(mt_file_pattern: str, n_runs: int = 1000) -> dict:
    '''Analyze Monte Carlo results for yield and sigma.'''
    results = []
    for i in range(n_runs):
        mt_file = mt_file_pattern.replace('*', str(i))
        if Path(mt_file).exists():
            df = parse_mt0(mt_file)
            results.append(df.iloc[0].to_dict())

    df = pd.DataFrame(results)

    analysis = {
        'n_runs': len(df),
        'mean': df.mean().to_dict(),
        'std': df.std().to_dict(),
        'min': df.min().to_dict(),
        'max': df.max().to_dict(),
    }

    # Failure rate analysis
    if 'FAIL_READ' in df.columns:
        analysis['fail_rate_read'] = df['FAIL_READ'].mean()
    if 'FAIL_WRITE' in df.columns:
        analysis['fail_rate_write'] = df['FAIL_WRITE'].mean()
    if 'FAIL_TOTAL' in df.columns:
        analysis['fail_rate_total'] = df['FAIL_TOTAL'].mean()
        # Array yield for N-bit SRAM
        n_cells = 1024 * 1024  # 1 Mbit
        p_cell = analysis['fail_rate_total']
        analysis['array_yield'] = (1 - p_cell) ** n_cells

    return analysis

# Usage
analysis = analyze_mc_results('sram_char.dc.mt*', n_runs=1000)
print(f'RSNM mean: {analysis[\"mean\"][\"RSNM\"]:.4f}')
print(f'Fail rate: {analysis[\"fail_rate_total\"]:.6f}')
print(f'Array yield (1Mb): {analysis[\"array_yield\"]:.4f}')
`

### 6.3 Vmin Extraction from Multi-VDD Monte Carlo
`python
def extract_vmin(mc_results: list) -> pd.DataFrame:
    '''
    Extract VMIN distribution from multi-VDD Monte Carlo data.
    
    Args:
        mc_results: List of dicts with 'vdd', 'FAIL_READ', 'FAIL_WRITE', 'FAIL_TOTAL'
    
    Returns:
        DataFrame with VMIN per trial
    '''
    df = pd.DataFrame(mc_results)
    
    # Find minimum VDD where cell passes all criteria
    vmin_per_trial = {}
    for trial_idx, trial_df in df.groupby('trial'):
        passing = trial_df[trial_df['FAIL_TOTAL'] == 0]
        if len(passing) > 0:
            vmin = passing['vdd'].min()
        else:
            vmin = trial_df['vdd'].max()  # Never passes
        vmin_per_trial[trial_idx] = vmin

    vmin_df = pd.DataFrame({
        'trial': list(vmin_per_trial.keys()),
        'vmin': list(vmin_per_trial.values())
    })

    # Statistics
    stats = {
        'mu_vmin': vmin_df['vmin'].mean(),
        'sigma_vmin': vmin_df['vmin'].std(),
        'vmin_6sigma': vmin_df['vmin'].mean() + 6 * vmin_df['vmin'].std(),
    }

    return vmin_df, stats
`

---

## 7. Complete Python Parsing Library Reference

### 7.1 Class Diagram
`
HspiceOutputParser
??? parse_mt0(filepath)       -> pd.DataFrame
??? parse_mc_runs(dir, base)  -> pd.DataFrame
??? parse_lis(filepath)       -> dict
??? parse_post_binary(filepath) -> dict
??? HspiceWorkbench
    ??? run_netlist(netlist) -> dict
    ??? run_sweep(template, params) -> pd.DataFrame
`

### 7.2 Unified Parser Class
`python
import re
import struct
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd

class HspiceOutputParser:
    '''Unified HSPICE output parser for all file types.
    
    Usage:
        parser = HspiceOutputParser()
        
        # Parse measurement results
        df = parser.parse_mt0('results.mt0')
        lis = parser.parse_lis('results.lis')
        
        # Parse Monte Carlo
        mc_df = parser.parse_mc_runs('./', 'results.dc.mt')
        mc_stats = parser.get_mc_statistics(mc_df)
        
        # Extract specific measures
        rsnm = parser.extract_measure('results.lis', 'rsnm')
    '''

    @staticmethod
    def parse_mt0(filepath: Union[str, Path]) -> pd.DataFrame:
        '''Parse .mt0/.st0 measurement file. Returns DataFrame.'''
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f'{filepath} not found')

        with open(path, 'r') as f:
            lines = f.readlines()

        # Find header and data
        header_idx = None
        for i, line in enumerate(lines):
            s = line.strip()
            if s and not s.startswith('$') and s.split()[0] == 'INDEX':
                header_idx = i
                break

        if header_idx is None:
            raise ValueError(f'No header in {filepath}')

        columns = lines[header_idx].split()
        data_rows = []
        for line in lines[header_idx + 1:]:
            s = line.strip()
            if not s or s.startswith('$'):
                continue
            vals = s.split()
            if len(vals) == len(columns):
                row = {}
                for c, v in zip(columns, vals):
                    try:
                        row[c] = float(v)
                    except ValueError:
                        row[c] = v
                data_rows.append(row)

        return pd.DataFrame(data_rows)

    @staticmethod
    def parse_lis(filepath: Union[str, Path]) -> Dict[str, float]:
        '''Extract .MEASURE results from .lis file.'''
        content = Path(filepath).read_text()
        measures = {}
        # Match 'name = value' patterns in measure section
        for match in re.finditer(
            r'^\s+(\w+)\s+=\s+([+-]?\d+\.?\d*[eE]?[+-]?\d*)',
            content, re.MULTILINE
        ):
            try:
                measures[match.group(1).lower()] = float(match.group(2))
            except ValueError:
                pass
        return measures

    @staticmethod
    def extract_measure(filepath: Union[str, Path], 
                        measure_name: str) -> Optional[float]:
        '''Extract a single .MEASURE value by name.'''
        measures = HspiceOutputParser.parse_lis(filepath)
        return measures.get(measure_name.lower())

    @staticmethod
    def parse_mc_runs(directory: Union[str, Path],
                      base_pattern: str = 'mt') -> pd.DataFrame:
        '''Parse Monte Carlo per-run files into DataFrame.'''
        path = Path(directory)
        files = sorted(path.glob(f'{base_pattern}*'))
        
        runs = []
        for f in files:
            try:
                df = HspiceOutputParser.parse_mt0(f)
                runs.append(df.iloc[0].to_dict())
            except (ValueError, IndexError):
                continue

        return pd.DataFrame(runs)

    @staticmethod
    def get_mc_statistics(df: pd.DataFrame) -> Dict[str, Dict]:
        '''Compute statistics for Monte Carlo results.'''
        stats = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            if col == 'INDEX':
                continue
            stats[col] = {
                'mean': float(df[col].mean()),
                'std': float(df[col].std()),
                'min': float(df[col].min()),
                'max': float(df[col].max()),
                'median': float(df[col].median()),
                'sigma_3': float(df[col].mean() - 3 * df[col].std()),
                'sigma_6': float(df[col].mean() - 6 * df[col].std()),
            }
        return stats

    @staticmethod
    def detect_failure(df: pd.DataFrame, 
                       conditions: Dict[str, tuple]) -> pd.Series:
        '''Detect failures based on comparison conditions.
        
        Args:
            df: Measurement DataFrame
            conditions: {'COLUMN': ('<|>|<=|>=', threshold)}
        
        Returns:
            Series: True if any condition is violated
        '''
        failures = pd.Series(False, index=df.index)
        for col, (op, threshold) in conditions.items():
            if op == '<':
                failures |= (df[col] < threshold)
            elif op == '>':
                failures |= (df[col] > threshold)
            elif op == '<=':
                failures |= (df[col] <= threshold)
            elif op == '>=':
                failures |= (df[col] >= threshold)
        return failures
`

### 7.3 Usage Examples for All Parsing Tasks
`python
# Initialize parser
parser = HspiceOutputParser()

# 1. Parse single DC measurement
df = parser.parse_mt0('sram_char.dc.mt0')
print(f'RSNM = {df.iloc[0][\"RSNM\"]:.3f}V')

# 2. Extract from .lis (backup method)
lis_vals = parser.parse_lis('sram_char.lis')
print(f'RSNM = {lis_vals[\"rsnm\"]:.3f}V')

# 3. Monte Carlo post-processing
mc_df = parser.parse_mc_runs('./', 'sram_char.dc.mt')
stats = parser.get_mc_statistics(mc_df)
print(f'RSNM: mu={stats[\"RSNM\"][\"mean\"]:.4f}, '
      f'sigma={stats[\"RSNM\"][\"std\"]:.4f}')
print(f'VMIN_6sigma = {stats[\"RSNM\"][\"sigma_6\"]:.3f}V')

# 4. Failure detection
conditions = {
    'RSNM': ('<', 0.08),    # Read failure
    'IREAD': ('<', 1e-6),   # Current failure
}
failures = parser.detect_failure(mc_df, conditions)
print(f'Failure rate: {failures.mean():.4f}')

# 5. Export to CSV for external analysis
mc_df.to_csv('mc_results.csv', index=False)
`

---

## 8. Integration with RAG System

### 8.1 Chunking Strategy for HSPICE Output RAG
For the Python RAG system, output parsing results should be chunked by:

- **Per-simulation chunks**: One chunk per simulation deck, containing key metrics
- **Per-measure chunks**: Individual .MEASURE results with value, unit, condition
- **Statistical chunks**: MC statistics (mu, sigma, min, max, sigma_3, sigma_6)

### 8.2 RAG-Ready Output Schema
`python
# Each parsed result follows this schema for RAG ingestion:
rag_document = {
    'id': 'sram_char_vdd08_tt_25c',
    'type': 'simulation_result',        # Document type
    'deck': 'sram_char.sp',             # Source netlist
    'corner': 'TT_25C',                 # PVT corner
    'analysis': 'DC',                   # Analysis type
    'measures': {
        'rsnm': {'value': 0.185, 'unit': 'V', 'pass': True},
        'iread': {'value': 3.21e-05, 'unit': 'A', 'pass': True},
        'wnm': {'value': 0.245, 'unit': 'V', 'pass': True},
        'vmin': {'value': 0.62, 'unit': 'V', 'pass': True},
    },
    'metadata': {
        'cpu_time_s': 0.25,
        'model': 'BSIM4 LEVEL=14',
        'vdd_nom': 0.8,
        'temperature': 25,
        'variation': 'MC_1000runs',
    },
    'statistics': {    # Monte Carlo only
        'rsnm': {'mu': 0.185, 'sigma': 0.012, 
                 'sigma_3': 0.149, 'sigma_6': 0.113},
        'vmin_read': {'mu': 0.62, 'sigma': 0.035,
                      'sigma_6': 0.83},
    }
}
`

### 8.3 Python RAG Ingestion Function
`python
import json
from datetime import datetime

def result_to_rag_document(mt0_df: pd.DataFrame,
                           lis_vals: dict,
                           deck_name: str,
                           corner: str = 'TT_25C') -> dict:
    '''Convert parsed HSPICE results to RAG-ready document.'''
    row = mt0_df.iloc[0] if not mt0_df.empty else {}

    measures = {}
    for col in mt0_df.columns:
        if col == 'INDEX':
            continue
        value = float(row[col]) if col in row else None
        measures[col.lower()] = {
            'value': value,
            'unit': 'V' if col.startswith('V') or 'SNM' in col or 'NM' in col 
                    else 'A' if col.startswith('I')
                    else '',
        }

    return {
        'id': f'{deck_name}_{corner}_{datetime.now().strftime(\"%Y%m%d\")}',
        'type': 'simulation_result',
        'deck': f'{deck_name}.sp',
        'corner': corner,
        'analysis': 'DC',
        'measures': measures,
        'metadata': {
            'cpu_time_s': lis_vals.get('cpu_time'),
            'vdd_nom': 0.8,
            'temperature': 25,
            'num_measures': len(measures),
        }
    }

# Batch conversion for RAG
def batch_to_rag(directory: str = '.') -> list:
    '''Convert all .mt0 files in directory to RAG documents.'''
    documents = []
    for mt_file in Path(directory).glob('*.mt0'):
        deck_name = mt_file.stem
        try:
            df = HspiceOutputParser.parse_mt0(str(mt_file))
            lis_file = mt_file.with_suffix('.lis')
            lis_vals = (HspiceOutputParser.parse_lis(str(lis_file))
                       if lis_file.exists() else {})
            
            doc = result_to_rag_document(df, lis_vals, deck_name)
            documents.append(doc)
        except Exception as e:
            print(f'Error parsing {mt_file}: {e}')

    return documents
`

### 8.4 Semantic Chunking for Embedding
`python
def chunk_for_rag(rag_doc: dict) -> list:
    '''Split RAG document into semantic chunks for embedding.'''
    chunks = []

    # Chunk 1: Summary
    chunks.append({
        'id': f'{rag_doc[\"id\"]}_summary',
        'text': (f'SRAM characterization at {rag_doc[\"corner\"]}. '
                 f'Deck: {rag_doc[\"deck\"]}. '
                 f'Analysis: {rag_doc[\"analysis\"]}.'),
        'metadata': rag_doc['metadata']
    })

    # Chunk 2: Individual measures
    for name, meas in rag_doc['measures'].items():
        chunks.append({
            'id': f'{rag_doc[\"id\"]}_{name}',
            'text': (f'{name.upper()} = {meas[\"value\"]:.4e} '
                     f'[{meas.get(\"unit\", \"\")}]'),
            'metadata': {'measure': name, **meas}
        })

    # Chunk 3: Statistics (if MC data exists)
    if 'statistics' in rag_doc:
        for name, stat in rag_doc['statistics'].items():
            chunks.append({
                'id': f'{rag_doc[\"id\"]}_{name}_stats',
                'text': (f'{name}: mu={stat[\"mu\"]:.4e}, '
                         f'sigma={stat[\"sigma\"]:.4e}, '
                         f'sigma_6={stat[\"sigma_6\"]:.4e}'),
                'metadata': {'measure': name, 'type': 'statistics'}
            })

    return chunks
`

---

> **Revision History**
> - 2026-06-30: Initial version. Covers .mt0, .lis, .tr0 parsing, Python library, RAG integration.
