       >>SOURCE FORMAT FREE
identification division.
program-id. PostingDriver.
environment division.
input-output section.
file-control.
    select account-index assign to ACCTFILE
      organization indexed access dynamic record key account-key
      file status account-fs.
    select xref-index assign to XREFFILE
      organization indexed access dynamic record key xref-key
      file status xref-fs.
    select category-index assign to TCATBALF
      organization indexed access dynamic record key category-key
      file status category-fs.
    select transaction-index assign to TRANFILE
      organization indexed access dynamic record key transaction-key
      file status transaction-fs.
    select daily-file assign to DALYTRAN
      organization sequential file status daily-fs.
    select rejects-file assign to DALYREJS
      organization sequential file status rejects-fs.
    select fixture-input assign to dynamic input-name
      organization line sequential file status input-fs.
    select output-lines assign to dynamic output-name
      organization line sequential file status output-fs.
data division.
file section.
fd account-index.
01 account-file-record.
   05 account-key pic 9(11).
   05 filler pic x(289).
fd xref-index.
01 xref-file-record.
   05 xref-key pic x(16).
   05 filler pic 9(9).
   05 xref-account pic 9(11).
   05 filler pic x(14).
fd category-index.
01 category-file-record.
   05 category-key pic x(17).
   05 filler pic x(33).
fd transaction-index.
01 transaction-file-record.
   05 transaction-key pic x(16).
   05 filler pic x(334).
fd daily-file.
01 daily-file-record pic x(350).
fd rejects-file.
01 rejects-file-record pic x(430).
fd fixture-input.
01 input-line pic x(1024).
fd output-lines.
01 output-line pic x(1024).
working-storage section.
       >>SOURCE FORMAT FIXED
       copy 'CVACT01Y.cpy'.
       copy 'CVACT03Y.cpy'.
       copy 'CVTRA01Y.cpy'.
       copy 'CVTRA05Y.cpy'.
       copy 'CVTRA06Y.cpy'.
       >>SOURCE FORMAT FREE
01 account-fs pic xx.
01 xref-fs pic xx.
01 category-fs pic xx.
01 transaction-fs pic xx.
01 daily-fs pic xx.
01 rejects-fs pic xx.
01 input-fs pic xx.
01 output-fs pic xx.
01 file-status pic xx.
01 input-name pic x(1024).
01 output-name pic x(1024).
01 action-name pic x(20).
01 eof-flag pic 9.
01 fields.
   05 field-value pic x(100) occurs 13.
01 amount-one pic +9(10).99.
01 amount-two pic +9(10).99.
01 amount-three pic +9(10).99.
01 amount-four pic +9(10).99.
01 amount-five pic +9(10).99.
01 amount-six pic +9(9).99.
01 reject-code pic x(4).
01 saved-return-code pic s9(4) comp.
01 external-parms.
   05 parm-length pic s9(4) comp value 10.
   05 parm-date pic x(10).
procedure division.
    accept action-name from command-line
    evaluate function trim(action-name)
      when 'seed'
        perform seed-accounts
        perform seed-xrefs
        perform seed-categories
        perform seed-daily-transactions
        perform seed-existing-transactions
      when 'run'
        call 'CBTRN02C' using external-parms
        move return-code to saved-return-code
        display 'CBTRN02C RETURN-CODE: ' saved-return-code
        move saved-return-code to return-code
        stop run
      when 'export'
        perform export-accounts
        perform export-category-balances
        perform export-transactions
        perform export-rejects
      when other
        display 'Expected seed, run or export'
        move 2 to return-code
        stop run
    end-evaluate
    move 0 to return-code
    stop run.
check-file.
    if file-status not = '00'
      display 'HARNESS FILE ERROR: ' file-status
      move 2 to return-code
      stop run
    end-if.
read-line.
    move spaces to input-line fields
    read fixture-input
      at end move 1 to eof-flag
      not at end
        unstring input-line delimited by '|'
          into field-value(1) field-value(2) field-value(3)
               field-value(4) field-value(5) field-value(6)
               field-value(7) field-value(8) field-value(9)
               field-value(10) field-value(11) field-value(12)
               field-value(13)
        end-unstring
    end-read
    if input-fs not = '00' and input-fs not = '10'
      move input-fs to file-status
      perform check-file
    end-if.
open-input.
    open input fixture-input
    move input-fs to file-status
    perform check-file
    move 0 to eof-flag.
write-output.
    write output-line
    if output-fs not = '00'
      move output-fs to file-status
      perform check-file
    end-if.
seed-accounts.
    accept input-name from environment 'REF_ACCOUNTS_INPUT'
    perform open-input
    open output account-index
    move account-fs to file-status
    perform check-file
    perform until eof-flag = 1
      perform read-line
      if eof-flag = 0
        initialize account-record
        move function numval(field-value(1)) to acct-id
        move field-value(2) to acct-group-id
        move function numval(field-value(3)) to acct-curr-bal
        move function numval(field-value(4)) to acct-curr-cyc-credit
        move function numval(field-value(5)) to acct-curr-cyc-debit
        move field-value(6) to acct-active-status
        move function numval(field-value(7)) to acct-credit-limit
        move function numval(field-value(8)) to acct-cash-credit-limit
        move field-value(9) to acct-open-date
        move field-value(10) to acct-expiraion-date
        move field-value(11) to acct-reissue-date
        move field-value(12) to acct-addr-zip
        write account-file-record from account-record
        move account-fs to file-status
        perform check-file
      end-if
    end-perform
    close fixture-input account-index.
seed-xrefs.
    accept input-name from environment 'REF_XREFS_INPUT'
    perform open-input
    open output xref-index
    move xref-fs to file-status
    perform check-file
    perform until eof-flag = 1
      perform read-line
      if eof-flag = 0
        initialize card-xref-record
        move field-value(1) to xref-card-num
        move function numval(field-value(2)) to xref-acct-id
        move function numval(field-value(3)) to xref-cust-id
        write xref-file-record from card-xref-record
        move xref-fs to file-status
        perform check-file
      end-if
    end-perform
    close fixture-input xref-index.
seed-categories.
    accept input-name from environment 'REF_CATEGORIES_INPUT'
    perform open-input
    open output category-index
    move category-fs to file-status
    perform check-file
    perform until eof-flag = 1
      perform read-line
      if eof-flag = 0
        initialize tran-cat-bal-record
        move function numval(field-value(1)) to trancat-acct-id
        move field-value(2) to trancat-type-cd
        move function numval(field-value(3)) to trancat-cd
        move function numval(field-value(4)) to tran-cat-bal
        write category-file-record from tran-cat-bal-record
        move category-fs to file-status
        perform check-file
      end-if
    end-perform
    close fixture-input category-index.
seed-daily-transactions.
    accept input-name from environment 'REF_TRANSACTIONS_INPUT'
    perform open-input
    open output daily-file
    move daily-fs to file-status
    perform check-file
    perform until eof-flag = 1
      perform read-line
      if eof-flag = 0
        initialize dalytran-record
        move field-value(1) to dalytran-id
        move field-value(2) to dalytran-type-cd
        move function numval(field-value(3)) to dalytran-cat-cd
        move field-value(4) to dalytran-source
        move field-value(5) to dalytran-desc
        move function numval(field-value(6)) to dalytran-amt
        move function numval(field-value(7)) to dalytran-merchant-id
        move field-value(8) to dalytran-merchant-name
        move field-value(9) to dalytran-merchant-city
        move field-value(10) to dalytran-merchant-zip
        move field-value(11) to dalytran-card-num
        move field-value(12) to dalytran-orig-ts
        move field-value(13) to dalytran-proc-ts
        write daily-file-record from dalytran-record
        move daily-fs to file-status
        perform check-file
      end-if
    end-perform
    close fixture-input daily-file.
seed-existing-transactions.
    accept input-name from environment 'REF_PRESEEDED_TRANSACTIONS_INPUT'
    perform open-input
    open output transaction-index
    move transaction-fs to file-status
    perform check-file
    perform until eof-flag = 1
      perform read-line
      if eof-flag = 0
        initialize tran-record
        move field-value(1) to tran-id
        move field-value(2) to tran-type-cd
        move function numval(field-value(3)) to tran-cat-cd
        move field-value(4) to tran-source
        move field-value(5) to tran-desc
        move function numval(field-value(6)) to tran-amt
        move function numval(field-value(7)) to tran-merchant-id
        move field-value(8) to tran-merchant-name
        move field-value(9) to tran-merchant-city
        move field-value(10) to tran-merchant-zip
        move field-value(11) to tran-card-num
        move field-value(12) to tran-orig-ts
        move field-value(13) to tran-proc-ts
        write transaction-file-record from tran-record
        move transaction-fs to file-status
        perform check-file
      end-if
    end-perform
    close fixture-input transaction-index.
export-accounts.
    accept output-name from environment 'REF_ACCOUNTS_OUTPUT'
    open output output-lines
    open input account-index
    move account-fs to file-status
    perform check-file
    perform until account-fs = '10'
      read account-index next record into account-record
      if account-fs = '00'
        move acct-curr-bal to amount-one
        move acct-curr-cyc-credit to amount-two
        move acct-curr-cyc-debit to amount-three
        move acct-credit-limit to amount-four
        move acct-cash-credit-limit to amount-five
        move spaces to output-line
        string acct-id '|' function trim(acct-group-id) '|'
          amount-one '|' amount-two '|' amount-three '|'
          acct-active-status '|' amount-four '|' amount-five '|'
          acct-open-date '|' acct-expiraion-date '|'
          acct-reissue-date '|' function trim(acct-addr-zip)
          delimited by size into output-line
        end-string
        perform write-output
      else
        if account-fs not = '10'
          move account-fs to file-status
          perform check-file
        end-if
      end-if
    end-perform
    close account-index output-lines.
export-category-balances.
    accept output-name from environment 'REF_CATEGORIES_OUTPUT'
    open output output-lines
    open input category-index
    move category-fs to file-status
    perform check-file
    perform until category-fs = '10'
      read category-index next record into tran-cat-bal-record
      if category-fs = '00'
        move tran-cat-bal to amount-six
        move spaces to output-line
        string trancat-acct-id '|' trancat-type-cd '|'
          trancat-cd '|' amount-six delimited by size
          into output-line
        end-string
        perform write-output
      else
        if category-fs not = '10'
          move category-fs to file-status
          perform check-file
        end-if
      end-if
    end-perform
    close category-index output-lines.
export-transactions.
    accept output-name from environment 'REF_TRANSACTIONS_OUTPUT'
    open output output-lines
    open input transaction-index
    move transaction-fs to file-status
    perform check-file
    perform until transaction-fs = '10'
      read transaction-index next record into tran-record
      if transaction-fs = '00'
        move tran-amt to amount-six
        inspect tran-desc replacing all low-values by spaces
        move spaces to output-line
        string tran-id '|' tran-type-cd '|' tran-cat-cd '|'
          function trim(tran-source) '|'
          function trim(tran-desc) '|' amount-six '|'
          tran-card-num '|' tran-orig-ts '|' tran-proc-ts '|'
          tran-merchant-id '|'
          function trim(tran-merchant-name) '|'
          function trim(tran-merchant-city) '|'
          function trim(tran-merchant-zip)
          delimited by size into output-line
        end-string
        perform write-output
      else
        if transaction-fs not = '10'
          move transaction-fs to file-status
          perform check-file
        end-if
      end-if
    end-perform
    close transaction-index output-lines.
export-rejects.
    accept output-name from environment 'REF_REJECTS_OUTPUT'
    open output output-lines
    open input rejects-file
    move rejects-fs to file-status
    perform check-file
    perform until rejects-fs = '10'
      read rejects-file
      if rejects-fs = '00'
        move rejects-file-record(1:350) to dalytran-record
        move rejects-file-record(351:4) to reject-code
        move dalytran-amt to amount-six
        move spaces to output-line
        string function trim(dalytran-id) '|'
          function trim(dalytran-card-num) '|' amount-six '|'
          dalytran-orig-ts '|' reject-code '|'
          function trim(rejects-file-record(355:76))
          delimited by size into output-line
        end-string
        perform write-output
      else
        if rejects-fs not = '10'
          move rejects-fs to file-status
          perform check-file
        end-if
      end-if
    end-perform
    close rejects-file output-lines.
