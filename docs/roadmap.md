# Roadmap

```{note}
We are just two tech nerds developing this baby in our free time, for fun.
```

Please don't take the roadmap too serious.
We wont give any estimates for _when_ things will happen, the roadmap is more of a priority list.

Our hope is that this will help others who want to contribute PRs to judge if their planned feature fits in, or if it requires preliminaries from our side.
If you are not sure, just open an issue to pitch your idea.


- **Plistsync v1.0**
    - Our other awesome music Project.
      We are close to the first major release.
      Go check it out ([click](https://github.com/metasauce/plistsync)).

- **Improved Backend API**
    - Document and stabilize the _beets library_ API. [#280][issue-280], [PR #345][pr-345]
    - Adapt this new format to our session endpoints.

- **Library Editor**
    - Edit info for already imported items, write back to beets and file meta data.
    - [#306][issue-306], [#332][issue-332], [#230][issue-230], [#319][issue-319]

- **Performance Tweaks**
    - Rewrite Terminal.
      Currently we are streaming every screen update via tmux.
      Should just use file sockets. [#199][issue-199], [#251][issue-251], [#282][issue-282]
    - Rewrite Watchdog.
      Currently runs quite a large copy of the full beetsflask.
      A simpler design could only monitor file changes, and ping the main app via api or redis. Then, the main thread handles the core logic. [#244][issue-244], [#202][issue-202]

- **Extension System**
    - Better support for beets plugins (via a new beetsflask extension system)
    - e.g. Authentication Providers [PR #339][pr-339], [PR #341][pr-341]

- **Inbox UX Improvements**
    - Improve initial setup for non-beets libraries. Currently, beetsflask struggles to deal with 50+ albums in the inbox.
      This makes it hard to use for new users who want to port an existing library. However, this is mainly an onboarding issue (and therefore low on our prio list :P - we have been running this day to day very happily) [#175][issue-175], [#164][issue-164], [#193][issue-193], [#344][issue-344]
    - Pagination. [#164][issue-164], [#351][issue-351], [#352][issue-352]
    - UX to select and action multiple or all albums. [#200][issue-200], [#201][issue-201], [#210][issue-210]
    - Filtering. [#209][issue-209]

- **Session Overview**
    - Similar to the inbox, but for sessions. Will also help with the onboarding library imports.
    - Shows folders that are identified as albums, and have (not) been imported or tagged.
    - [#193][issue-193]



<!-- PR links -->
[pr-339]: https://github.com/metasauce/beets-flask/pull/339
[pr-341]: https://github.com/metasauce/beets-flask/pull/341
[pr-345]: https://github.com/metasauce/beets-flask/pull/345

<!-- Issue links -->
[issue-164]: https://github.com/metasauce/beets-flask/issues/164
[issue-175]: https://github.com/metasauce/beets-flask/issues/175
[issue-193]: https://github.com/metasauce/beets-flask/issues/193
[issue-199]: https://github.com/metasauce/beets-flask/issues/199
[issue-200]: https://github.com/metasauce/beets-flask/issues/200
[issue-201]: https://github.com/metasauce/beets-flask/issues/201
[issue-202]: https://github.com/metasauce/beets-flask/issues/202
[issue-209]: https://github.com/metasauce/beets-flask/issues/209
[issue-210]: https://github.com/metasauce/beets-flask/issues/210
[issue-230]: https://github.com/metasauce/beets-flask/issues/230
[issue-244]: https://github.com/metasauce/beets-flask/issues/244
[issue-251]: https://github.com/metasauce/beets-flask/issues/251
[issue-280]: https://github.com/metasauce/beets-flask/issues/280
[issue-282]: https://github.com/metasauce/beets-flask/issues/282
[issue-306]: https://github.com/metasauce/beets-flask/issues/306
[issue-319]: https://github.com/metasauce/beets-flask/issues/319
[issue-332]: https://github.com/metasauce/beets-flask/issues/332
[issue-344]: https://github.com/metasauce/beets-flask/issues/344
[issue-351]: https://github.com/metasauce/beets-flask/issues/351
[issue-352]: https://github.com/metasauce/beets-flask/issues/352
