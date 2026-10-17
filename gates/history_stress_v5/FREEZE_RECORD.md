# Freeze record: history stress test v5 (CANDIDATE)

**Status: freeze candidate. GPU execution is NOT approved.** Nothing in this record is a model
output. Proposal: `docs/HISTORY_STRESS_TEST_V5_PROPOSAL.md`. Review record:
`gates/redteam/trigger4-history-positive-control-v5-2026-10-17.md`.

## In the repository
| Path | sha256 |
|---|---|
| `scripts/history_sensitivity/history_runner.py` | `288b6cf71814e6057cb9ce4a05d05960ffe38c241cd523e91ff5187346c20f74` |
| `scripts/history_sensitivity/test_history_runner.py` | `c9c54203b4c53062287c71c8a5312da40326aff2bfcc360d730bdd7d22d5e75d` |
| `scripts/history_sensitivity/history_substitutes.py` (test only) | `fa56cdd57aab5b47851670703ce19e412211a817f5265de51b5703f52d09aa21` |
| `scripts/history_sensitivity/build_history_stress_manifest_v5.py` | `1a0194bfce07ce10e4dc4cdc9fcfcf714265ef1855a82768a6b7e15ed29da436` |

## Pinned inputs
| Item | sha256 |
|---|---|
| v5 call manifest (external, 256 calls) | `294e726d193b46d4ffa6dbb0bae6e479b4f76383ed735d7f1032173fc93418c7` |
| Source v3 manifest (external) | `391c2f02a944cd46f3683f53e4979041b34bad9060f035cf779fd283781ccfa7` |
| H5 synthetic frame bytes (uint8, 240×320×3, value 128) | `06d4819637d1c753371096aae289b573bbfcb238abd672521369dbc9dc376469` |
| ViNT checkpoint `option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth` | `c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c` |

## External preparation evidence (not committed)
Location: `$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-prep-20261017/`. The directory
name keeps its original "positive-control" wording as a historical path.

It holds:
- the v5 manifest, and the superseded 184-call draft `b58cf90a…`;
- the build logs;
- the test logs and JUnit XML, with tested-source digests;
- the review reports.

`SHA256SUMS` sha256: `49eed366712effa5a28e124f9de36dbd8ce1e89c9bb78b9e31c96550188078fc`. Its contents:

```
83b8c63811b3ea12ca07da72df7b0c05fb12dc8a3e03068e7fc8e40d6aadd286  ./build_v5.log
2bce0d677b7e481ad7bca5bda157b3ebfeb4ca302a83ab449513e71de69aa320  ./build_v5_stress.log
b58cf90a97f562e7cd4353112e0c47810310f8e57805194d98b9207ec0330d61  ./history_call_manifest_v5_pc.json
294e726d193b46d4ffa6dbb0bae6e479b4f76383ed735d7f1032173fc93418c7  ./history_call_manifest_v5_stress.json
838279fa6ab629ddad4f8ac1bb8e267c378dc9b93736e594515ed21d7cc830f1  ./review_trigger4_v5_closure.md
e778ef2526d275bb7a2f7d5e45c2121d4f80cf06d38d99f5ac0f1f2a982db159  ./review_trigger4_v5_round1.md
ecee5e5b4fa3ae77ddcab81cbc7f9818961e2163e14291ac9f1eae8d23616550  ./review_trigger4_v5_round2.md
9cf06c30c39e3ca492ae7100180ba416b1fdabb3c7884b49117fbe42d83e9ef3  ./tested_sources_run1.sha256
f97b88e6e898a10de531b02e9cc5f89d44f3ca8f7a688e0a84d998a18d06ca92  ./tested_sources_run2.sha256
4c7f1b7e5299687517b1c1e5d441dd40698024e038590e6c28e5b4abc72a854b  ./tested_sources_run3.sha256
d73fbe14e7685b2ee36d8cd5f24ecf0baef0a0d4edaaf5dc741df4c7140e400b  ./tested_sources_run4.sha256
8e3ea89ad1a88c84263ac454c9954af1287dfd0e32f0c2c3b95a7586a0da4e43  ./tested_sources_stress_run1.sha256
901b92a2b9fcdbf61be7b628f683bcb006597a04ac594e0bfff0d86d7cbc2229  ./tested_sources_stress_run2.sha256
720df1e7fcc6afe23772e512a861c23e29cc1cfc8568fc774502911c46252df9  ./test_run1_junit.xml
a5f6691ca11c4c9ec79663c8f991be7e557ee2b5551ee67574ed00102b327cca  ./test_run1.log
103717d543d274d1b527eb6798df3e821df06f8fa972c65258150387fff3d1cc  ./test_run2_junit.xml
778fac1ffb21303bd564be458f22a948bcf813383da01caa70ab12fdfad6c8e3  ./test_run2.log
4eb0de2164af6e622152793a095d82b9b2892a13b0f1f0b8b600485f53855b3d  ./test_run3_junit.xml
39803eee55e2c14ba46b653981f858607cfb3ab95572269551b5a27244955da7  ./test_run3.log
499487102c6667a99449c016dab877489a45a529696a7862946b6081f2c829e8  ./test_run4_junit.xml
a6e553545481250ac95972c3f227c93646ba510161fbfe55e6ec0309c97cd3f6  ./test_run4.log
10c99b1d929d78a1a9c488c56cec96b5d2ccfdbdf943a45e935b80ee2f0c517b  ./test_stress_run1_junit.xml
4bc715e523d62a2cb04e88f0d555f37beddfb130d017b82af87f4d1e9007eefa  ./test_stress_run1.log
8ead4924276fb0197ac41851e48b2d1c12c430632b8730fe841bcebbdce2a07a  ./test_stress_run2_junit.xml
dcc8bffa09938ada980acdf0a924c513f04d9cbe36f2e4c0212b56e42d6b0911  ./test_stress_run2.log
```

## Proposed execution (NOT approved)
One attempt, exactly 256 calls, under the unchanged v4 resource limits:
- forward accounting with the cap equal to the 256 listed calls and an absolute ceiling of 320;
- a 600 s wall clock;
- a 4 GiB PyTorch-allocator cap and the sampled process-memory guard;
- no retries.

The command is in the proposal's "Freeze candidate" section. Check free disk space before
launch.
