# RFC 8785 canonicalization fixed-vector verification (function copied verbatim from runner/wrapper).
$ErrorActionPreference = 'Continue'

function ConvertTo-CanonicalJson([object]$Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [bool]) { return $(if ($Value) { 'true' } else { 'false' }) }
    if ($Value -is [string]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('"')
        foreach ($ch in $Value.ToCharArray()) {
            switch ($ch) {
                '"'  { [void]$sb.Append('\"') }
                '\'  { [void]$sb.Append('\\') }
                "`b" { [void]$sb.Append('\b') }
                "`f" { [void]$sb.Append('\f') }
                "`n" { [void]$sb.Append('\n') }
                "`r" { [void]$sb.Append('\r') }
                "`t" { [void]$sb.Append('\t') }
                default { if ([int]$ch -lt 0x20) { [void]$sb.Append('\u' + ([int]$ch).ToString('x4')) } else { [void]$sb.Append($ch) } }
            }
        }
        [void]$sb.Append('"')
        return $sb.ToString()
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $ht = @{}
        foreach ($p in $Value.PSObject.Properties) { $ht[$p.Name] = $p.Value }
        return (ConvertTo-CanonicalJson $ht)
    }
    if ($Value -is [System.Collections.IDictionary]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('{')
        $first = $true
        $keyArray = @($Value.Keys | ForEach-Object { [string]$_ })
        [System.Array]::Sort($keyArray, [System.StringComparer]::Ordinal)
        foreach ($k in $keyArray) {
            if (-not $first) { [void]$sb.Append(',') }
            [void]$sb.Append((ConvertTo-CanonicalJson $k))
            [void]$sb.Append(':')
            [void]$sb.Append((ConvertTo-CanonicalJson $Value[$k]))
            $first = $false
        }
        [void]$sb.Append('}')
        return $sb.ToString()
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        $sb = New-Object System.Text.StringBuilder
        [void]$sb.Append('[')
        $first = $true
        foreach ($item in $Value) { if (-not $first) { [void]$sb.Append(',') }; [void]$sb.Append((ConvertTo-CanonicalJson $item)); $first = $false }
        [void]$sb.Append(']')
        return $sb.ToString()
    }
    if ($Value -is [double] -or $Value -is [single]) { return ([string]$Value).ToLowerInvariant() }
    if ($Value -is [int] -or $Value -is [long] -or $Value -is [decimal] -or $Value -is [byte]) { return [string]$Value }
    return (ConvertTo-CanonicalJson ([string]$Value))
}

# fixed vectors
$vectors = @(
    @{ name='sort_keys'; input=@{ b=1; a=2 }; expect='{"a":2,"b":1}' },
    @{ name='unicode_raw'; input=@{ a=[char]0x00E9 }; expect=('{"a":"' + [char]0x00E9 + '"}') },
    @{ name='control_escape'; input=@{ a="line`nbreak" }; expect='{"a":"line\nbreak"}' },
    @{ name='quote_slash'; input=@{ a='q"b\s' }; expect='{"a":"q\"b\\s"}' },
    @{ name='nested_array'; input=@{ a=$true; b=$null; c=@(1,2); d=@{ z=9; a=8 } }; expect='{"a":true,"b":null,"c":[1,2],"d":{"a":8,"z":9}}' },
    @{ name='empty'; input=@{}; expect='{}' }
)
foreach ($v in $vectors) {
    $actual = ConvertTo-CanonicalJson $v.input
    $ok = ($actual -ceq $v.expect)
    Write-Output ("RFC8785_{0} pass={1} actual={2} expect={3}" -f $v.name, $ok, $actual, $v.expect)
}
Write-Output "RFC8785_VECTORS_DONE"
