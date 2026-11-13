% cvtdocs.cls - shared class of the four project books (ds, tm, um, cr).
% Engine: lualatex. No shell escape is needed.
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{cvtdocs}[2000/01/01 Project documentation class]

% Book selection: \documentclass[book=ds]{cvtdocs}
\def\cvtbook{ds}
\def\cvtbooktitle{Design Specification}
\def\cvtbookid{CVT-DS}
\DeclareOption{book=ds}{%
  \def\cvtbook{ds}\def\cvtbooktitle{Design Specification}\def\cvtbookid{CVT-DS}}
\DeclareOption{book=tm}{%
  \def\cvtbook{tm}\def\cvtbooktitle{Technical Manual}\def\cvtbookid{CVT-TM}}
\DeclareOption{book=um}{%
  \def\cvtbook{um}\def\cvtbooktitle{User Manual}\def\cvtbookid{CVT-UM}}
\DeclareOption{book=cr}{%
  \def\cvtbook{cr}\def\cvtbooktitle{Changes Record}\def\cvtbookid{CVT-CR}}
\ProcessOptions\relax
\LoadClass[a4paper,11pt,oneside]{report}

% Revision string. The build driver defines \cvtrevision on the command line.
\providecommand{\cvtrevision}{unversioned}
% Directory of the aux files of all books, relative to the working directory.
\providecommand{\cvtauxroot}{..}

\RequirePackage{iftex}
\RequireLuaTeX
\RequirePackage[a4paper,margin=25mm,headheight=14pt]{geometry}
\RequirePackage{fontspec}
\setmainfont{Latin Modern Roman}
\setsansfont{Latin Modern Sans}
% Monospace: DejaVu Sans Mono (package dejavu in MiKTeX and TeX Live). It has the
% box-drawing and block characters of the code diagrams; Latin Modern Mono has not.
% The scale gives the same character width as Latin Modern Mono.
\setmonofont{DejaVuSansMono}[Extension=.ttf,UprightFont=*,BoldFont=*-Bold,
  ItalicFont=*-Oblique,BoldItalicFont=*-BoldOblique,Scale=0.87]
% Symbols that Latin Modern lacks come from DejaVu Sans.
\newfontfamily\cvtfallbackfont{DejaVuSans}[Extension=.ttf,UprightFont=*,
  BoldFont=*-Bold,ItalicFont=*-Oblique,BoldItalicFont=*-BoldOblique,Scale=0.95]
\RequirePackage{amsmath}
\RequirePackage{amssymb}
% Symbols that Latin Modern text fonts lack come from the math fonts.
\RequirePackage{newunicodechar}
% \cvtsym{hex}{text}: in monospace text print the glyph of DejaVu Sans Mono,
% otherwise print the text. The glyph is taken by number, so the definition
% does not call itself.
\newcommand{\cvtsym}[2]{\ifx\f@family\ttdefault\char#1\relax\else#2\fi}
\newcommand{\cvtfb}[1]{{\cvtfallbackfont\char#1\relax}}
\newunicodechar{≥}{\cvtsym{"2265}{\ensuremath{\geq}}}
\newunicodechar{≤}{\cvtsym{"2264}{\ensuremath{\leq}}}
\newunicodechar{→}{\cvtsym{"2192}{\ensuremath{\rightarrow}}}
\newunicodechar{←}{\cvtsym{"2190}{\ensuremath{\leftarrow}}}
\newunicodechar{↔}{\cvtsym{"2194}{\ensuremath{\leftrightarrow}}}
\newunicodechar{⇒}{\cvtsym{"21D2}{\ensuremath{\Rightarrow}}}
\newunicodechar{≈}{\cvtsym{"2248}{\ensuremath{\approx}}}
\newunicodechar{≠}{\cvtsym{"2260}{\ensuremath{\neq}}}
\newunicodechar{∈}{\cvtsym{"2208}{\ensuremath{\in}}}
\newunicodechar{Δ}{\cvtsym{"0394}{\ensuremath{\Delta}}}
\newunicodechar{μ}{\cvtsym{"03BC}{\ensuremath{\mu}}}
\newunicodechar{✓}{\cvtsym{"2713}{\ensuremath{\checkmark}}}
\newunicodechar{✗}{\cvtsym{"2717}{\cvtfb{"2717}}}
\newunicodechar{✘}{\cvtsym{"2718}{\cvtfb{"2718}}}
\newunicodechar{☐}{\cvtsym{"2610}{\cvtfb{"2610}}}
\newunicodechar{☑}{\cvtsym{"2611}{\cvtfb{"2611}}}
\newunicodechar{☒}{\cvtsym{"2612}{\cvtfb{"2612}}}
\newunicodechar{►}{\cvtsym{"25BA}{\cvtfb{"25BA}}}
\newunicodechar{◄}{\cvtsym{"25C4}{\cvtfb{"25C4}}}
\newunicodechar{▲}{\cvtsym{"25B2}{\cvtfb{"25B2}}}
\newunicodechar{▼}{\cvtsym{"25BC}{\cvtfb{"25BC}}}
\newunicodechar{⁰}{\cvtsym{"2070}{\textsuperscript{0}}}
\newunicodechar{⁴}{\cvtsym{"2074}{\textsuperscript{4}}}
\newunicodechar{⁵}{\cvtsym{"2075}{\textsuperscript{5}}}
\newunicodechar{⁶}{\cvtsym{"2076}{\textsuperscript{6}}}
\newunicodechar{⁷}{\cvtsym{"2077}{\textsuperscript{7}}}
\newunicodechar{⁸}{\cvtsym{"2078}{\textsuperscript{8}}}
\newunicodechar{⁹}{\cvtsym{"2079}{\textsuperscript{9}}}
\newunicodechar{₀}{\cvtsym{"2080}{\textsubscript{0}}}
\newunicodechar{₁}{\cvtsym{"2081}{\textsubscript{1}}}
\newunicodechar{₂}{\cvtsym{"2082}{\textsubscript{2}}}
\newunicodechar{₃}{\cvtsym{"2083}{\textsubscript{3}}}
\newunicodechar{₄}{\cvtsym{"2084}{\textsubscript{4}}}
\newunicodechar{₅}{\cvtsym{"2085}{\textsubscript{5}}}
\newunicodechar{₆}{\cvtsym{"2086}{\textsubscript{6}}}
\newunicodechar{₇}{\cvtsym{"2087}{\textsubscript{7}}}
\newunicodechar{₈}{\cvtsym{"2088}{\textsubscript{8}}}
\newunicodechar{₉}{\cvtsym{"2089}{\textsubscript{9}}}
\RequirePackage{xcolor}
\RequirePackage{graphicx}
\RequirePackage{array}
\RequirePackage{calc}% pandoc table columns use \real
\RequirePackage[normalem]{ulem}% pandoc strikeout
\RequirePackage{longtable}
\RequirePackage{booktabs}
\RequirePackage{pdflscape}
\RequirePackage{enumitem}
\RequirePackage{fancyhdr}
\RequirePackage{fvextra}
\RequirePackage{listings}
\RequirePackage{imakeidx}
\RequirePackage{xr-hyper}
\RequirePackage[unicode,colorlinks=true,
  linkcolor=blue!50!black,citecolor=blue!50!black,urlcolor=blue!50!black,
  bookmarksnumbered=true]{hyperref}
\RequirePackage{xurl}% long URLs break at any character
\RequirePackage[capitalise,noabbrev]{cleveref}
\RequirePackage[acronym,toc=false]{glossaries-extra}
\setabbreviationstyle[acronym]{long-short}

\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6ex plus 0.2ex minus 0.1ex}
\setlist{nosep,leftmargin=*}
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{2}
\emergencystretch=3em

% Pandoc output support.
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\providecommand{\pandocbounded}[1]{#1}
\providecommand{\passthrough}[1]{#1}
\newcounter{none}% pandoc sets \LTcaptype to none for unnumbered tables
\providecommand{\textsubscript}[1]{\ensuremath{{}_{\mathrm{#1}}}}

% Running heads.
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.3pt}
\fancyhead[L]{\small\cvtbooktitle}
\fancyhead[R]{\small\nouppercase{\leftmark}}
\fancyfoot[L]{\small\texttt{\cvtrevision}}
\fancyfoot[R]{\small\thepage}
\fancypagestyle{plain}{%
  \fancyhf{}\renewcommand{\headrulewidth}{0pt}%
  \fancyfoot[L]{\small\texttt{\cvtrevision}}\fancyfoot[R]{\small\thepage}}

% Title page: \cvtmaketitle{title}{identifier}{revision}
\newcommand{\cvtmaketitle}[3]{%
  \hypersetup{pdftitle={#1},pdfauthor={Project documentation},
    pdfsubject={#2, revision #3}}%
  \begin{titlepage}
    \raggedright
    \vspace*{30mm}
    {\sffamily\bfseries\fontsize{30}{34}\selectfont #1\par}
    \vspace{8mm}
    {\sffamily\Large RV32I CPU and GPU-lite SoC\par}
    \vfill
    \begin{tabular}{@{}ll@{}}
      Document identifier & \texttt{#2}\\
      Revision & \texttt{#3}
    \end{tabular}
  \end{titlepage}}

% Cross-book references (xr-hyper): \cvtexternal{tm}
\newcommand{\cvtexternal}[1]{%
  \externaldocument{\cvtauxroot/#1/#1}[#1.pdf]}

% Bead index of the book.
\edef\cvtbeadindex{\cvtbook beads}

\RequirePackage{cvtmacros}
\endinput
